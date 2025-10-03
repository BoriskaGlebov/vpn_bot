import asyncio
import ipaddress
import json
import random
import shlex
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import AsyncGenerator, List, Optional, Tuple, Type

import aiofiles  # type: ignore
import asyncssh

from bot.config import logger


class AsyncSSHClient:
    """Асинхронный SSH-клиент с поддержкой работы через Docker-контейнер.

    Args:
        host (str): Адрес сервера (IP или DNS).
        username (str): Имя пользователя.
        port (int, optional): SSH-порт. По умолчанию 22.
        key_filename (Optional[str], optional): Путь к приватному ключу.
            Если None, будут использоваться ключи из ``~/.ssh``.
        known_hosts (Optional[str], optional): Путь к файлу ``known_hosts``.
            Если None, проверка отключается.
        container (str, optional): Имя контейнера Docker, в котором
            будут выполняться команды. По умолчанию "amnezia-awg".

    """

    WG_DIR = "/opt/amnezia/awg"
    WG_CONF = f"{WG_DIR}/wg0.conf"

    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        key_filename: Optional[str] = None,
        known_hosts: Optional[str] = None,
        container: str = "amnezia-awg",
        config_port: int = 32349,
    ) -> None:
        self.host = host
        self.username = username
        self.port = port
        self.key_filename = key_filename
        self.known_hosts = known_hosts
        self.container = container
        self.config_port = config_port
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._process: Optional[asyncssh.SSHClientProcess] = None

    async def connect(self) -> None:
        """Устанавливает SSH-соединение и открывает shell-сессию.

        Raises
           OSError: Ошибка на уровне сокета или ОС.
           Asyncssh.Error: Ошибка внутри библиотеки ``asyncssh``.

        """
        if self._conn is not None:
            logger.bind(user=self.username).debug("AsyncSSH: уже подключён")
            return

        try:
            self._conn = await asyncssh.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                client_keys=[self.key_filename] if self.key_filename else None,
                known_hosts=self.known_hosts,
            )
            self._process = await self._conn.create_process(
                f"docker exec -i {self.container} sh;\n"
            )
            logger.bind(user=self.username).debug(
                f"AsyncSSH: подключение и shell-сессия установлены к {self.host}"
            )
        except (OSError, asyncssh.Error) as exc:
            logger.bind(user=self.username).error(
                f"AsyncSSH: ошибка подключения: {exc}"
            )
            raise

    async def write_single_cmd(self, cmd: str) -> Tuple[str, str, int, str]:
        """Выполняет одну команду внутри контейнера.

        Args:
            cmd (str): Команда для выполнения.

        Returns
            Tuple[str, str, int, str]: Кортеж:
                - stdout (str): Стандартный вывод команды.
                - stderr (str): Стандартный поток ошибок.
                - exit_code (int): Код возврата команды.
                - cmd (str): Выполненная команда.

        Raises
            RuntimeError: Если shell-сессия не запущена.

        """
        if self._process is None:
            raise RuntimeError("AsyncSSH: shell-сессия не запущена. Вызови connect()")
        marker = "__EXIT__"
        self._process.stdin.write(f"{cmd}; echo {marker}:$?\n")
        await self._process.stdin.drain()
        output = await self._process.stdout.readuntil("\n")
        while marker not in output:
            output += await self._process.stdout.readuntil("\n")
        stdout, _, exit_info = output.rpartition("__EXIT__")
        try:
            exit_code = int(exit_info.split(":")[-1])
        except ValueError:
            exit_code = 0
        stderr = ""
        try:
            while True:
                line = await asyncio.wait_for(
                    self._process.stderr.readline(), timeout=0.1
                )
                if not line:
                    break
                stderr += line
        except asyncio.TimeoutError:
            pass

        return stdout.strip(), stderr.strip(), exit_code, cmd

    async def run_commands_in_container(
        self, commands: List[str]
    ) -> AsyncGenerator[Tuple[str, str, int, str], None]:
        """Выполняет список команд внутри контейнера.

        Args:
            commands (List[str]): Список команд для выполнения.

        Yields
            Tuple[str, str, int, str]: stdout, stderr, exit_code, команда.

        """
        for cmd in commands:
            stdout, stderr, exit_code, cmd = await self.write_single_cmd(cmd)
            yield stdout, stderr, exit_code, cmd

    async def check_container(self) -> bool:
        """Проверяет доступность контейнера.

        Returns
           bool: True, если контейнер доступен и команда `whoami` вернула "root".

        """
        stdout, *_ = await self.write_single_cmd("whoami")
        if stdout == "root":
            logger.debug("Проверка контейнера прошла успешно")
            return True
        else:
            logger.error(f"Проверка контейнера не пройдена. Ответ: {stdout}")
            return False

    async def generate_private_key(self) -> Optional[str]:
        """Генерирует приватный ключ в контейнере.

        Returns
           Optional[str]: Приватный ключ или None, если не удалось получить.

        """
        cmd = [
            f"cd {self.WG_DIR}",
            "wg genkey > privetkey",
            "cat privetkey",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                return stdout
            if stderr:
                logger.bind(user=self.username).error(
                    f"Ошибка при генерации ключа: {stderr}"
                )
        return None

    async def generate_public_key(self) -> Optional[str]:
        """Генерирует публичный ключ из приватного.

        Returns
            Optional[str]: Публичный ключ или None, если не удалось получить.

        """
        cmd = [
            "cat privetkey | wg pubkey > publickey",
            "cat publickey",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                return stdout
            if stderr:
                logger.bind(user=self.username).error(
                    f"Ошибка при генерации публичного ключа: {stderr}"
                )
        return None

    async def get_correct_ip(self) -> Optional[str]:
        """Определяет корректный IP-адрес клиента для WireGuard.

        Returns
           Optional[str]: IP-адрес в формате "x.x.x.x/32" или None.

        """
        cmd = [
            f"cat {self.WG_CONF} | grep 'AllowedIPs =' | tail -n 1 | awk '{{print $3}}'>lastip",
            "cat lastip",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                try:
                    ip_str = stdout.rpartition("/")[0]
                    ip_correct = ipaddress.ip_address(ip_str) + 1
                    return f"{ip_correct}/32"
                except ValueError:
                    logger.bind(user=self.username).error(f"Некорректный IP: {stdout}")
                    return None
            if stderr:
                logger.bind(user=self.username).error(
                    f"Ошибка при получении IP: {stderr}"
                )
        return None

    async def get_psk_key(self) -> Optional[str]:
        """Определяет preshared_key от  WireGuard.

        Returns
           Optional[str]: preshared_key или None.

        """
        stdout, stderr, *_ = await self.write_single_cmd("cat wireguard_psk.key")
        if stdout:
            return stdout
        if stderr:
            logger.bind(user=self.username).error(f"Ошибка при получении PSK: {stderr}")
        return None

    async def get_public_server_key(self) -> Optional[str]:
        """Определяет public_key от  WireGuard сервера.

        Returns
           Optional[str]: public_key или None.

        """
        stdout, stderr, *_ = await self.write_single_cmd(
            "cat wireguard_server_public_key.key"
        )
        if stdout:
            return stdout
        if stderr:
            logger.bind(user=self.username).error(
                f"Ошибка при получении public key сервера: {stderr}"
            )
        return None

    async def add_user_in_config(
        self, public_server_key: str, correct_ip: str, psk_key: str
    ) -> Optional[str]:
        """Добавляет конфигурацию пользователя в `wg0.conf`.

        Args:
            public_server_key (str): Публичный ключ клиента.
            correct_ip (str): IP-адрес клиента.
            psk_key (str): preshared key.

        Returns
            Optional[str]: "OK", если успешно, иначе None.

        """
        cmd = [
            f'echo " " >> {self.WG_CONF}',
            f'echo "[Peer]" >> {self.WG_CONF}',
            f'echo "PublicKey = {public_server_key}" >> {self.WG_CONF}',
            f'echo "PresharedKey = {psk_key}" >> {self.WG_CONF}',
            f'echo "AllowedIPs = {correct_ip}" >> {self.WG_CONF}',
            "echo OK",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                return stdout
            if stderr:
                logger.bind(user=self.username).error(
                    f"Ошибка при добавлении пользователя: {stderr}"
                )

        return None

    async def generate_wg_config(
        self, new_ip: str, private_key: str, pub_server_key: str, preshared_key: str
    ) -> str:
        """Создает содержимое пользовательского файла конфигурации WireGuard.

        Args:
            new_ip (str): корректный IP-адрес для пользователя
            private_key (str): приватный ключ пользователя
            pub_server_key (str): публичный ключ сервера
            preshared_key (str): PSK ключ сервера

        Returns
            str: Текст конфигурации WireGuard.

        """
        interface_data = {
            "Address": new_ip,
            "DNS": "1.1.1.1, 1.0.0.1",
            "PrivateKey": private_key,
            "Jc": "4",
            "Jmin": "10",
            "Jmax": "50",
            "S1": "18",
            "S2": "55",
            "H1": "1424794322",
            "H2": "642222786",
            "H3": "149027654",
            "H4": "180190564",
        }

        peer_data = {
            "PublicKey": pub_server_key,
            "PresharedKey": preshared_key,
            "AllowedIPs": "0.0.0.0/0, ::/0",
            "Endpoint": f"{self.host}:{self.config_port}",
            "PersistentKeepalive": "25",
        }

        lines = ["[Interface]"]
        for key, value in interface_data.items():
            lines.append(f"{key} = {value}")

        lines.append("")

        lines.append("[Peer]")
        for key, value in peer_data.items():
            lines.append(f"{key} = {value}")

        return "\n".join(lines)

    async def save_wg_config(
        self,
        filename: str,
        new_ip: str,
        private_key: str,
        pub_server_key: str,
        preshared_key: str,
    ) -> bool:
        """Создает и сохраняет пользовательский конфиг, затем перезапускает интерфейс.

        Args:
            filename (str): Название файла конфигурации.
            new_ip (str): IP-адрес пользователя.
            private_key (str): Приватный ключ пользователя.
            pub_server_key (str): Публичный ключ сервера.
            preshared_key (str): PSK ключ сервера.

        Returns
            bool: True, если конфиг создан и интерфейс перезапущен.

        """
        config_text = await self.generate_wg_config(
            new_ip, private_key, pub_server_key, preshared_key
        )
        file_dir = Path(__file__).resolve().parent / "user_cfg"
        file_dir.mkdir(parents=True, exist_ok=True)
        file_cfg = (
            file_dir / filename
            if filename.rsplit(".", 1)[-1] == "conf"
            else file_dir / f"{filename}.conf"
        )
        async with aiofiles.open(file_cfg, "w", encoding="utf-8") as f:
            await f.write(config_text)
        cmd = [f"wg-quick down {self.WG_CONF}", f"wg-quick up {self.WG_CONF}"]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                logger.bind(user=self.username).success(
                    f"Интерфейс выключен/включен:\n{stdout}"
                )
            if stderr:
                logger.bind(user=self.username).error(
                    f"Ошибка при перезапуске интерфейса: {stderr}"
                )
            await asyncio.sleep(3)
            await asyncio.sleep(3)
        return True

    async def add_to_clients_table(self, public_key: str, client_name: str) -> bool:
        """Добавляет запись в clientsTable Amnezia.

        Args:
            public_key (str): Публичный ключ клиента (clientId).
            client_name (str): Имя клиента (userData.clientName).

        Returns
            bool: True если запись добавлена.

        """
        clients_table = f"{self.WG_DIR}/clientsTable"
        # Считаем текущий JSON
        stdout, stderr, code, _ = await self.write_single_cmd(f"cat {clients_table}")
        if code != 0 or not stdout:
            logger.error(f"Не удалось прочитать clientsTable: {stderr}")
            return False

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга clientsTable: {e}")
            return False
        # Добавим, если нет дубликата
        if any(item.get("clientId") == public_key for item in data):
            logger.info("Клиент уже в clientsTable")
            return True

        # Добавляем новую запись с датой создания
        creation_date = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
        data.append(
            {
                "clientId": public_key,
                "userData": {"clientName": client_name, "creationDate": creation_date},
            }
        )
        new_json = json.dumps(data, indent=4, ensure_ascii=False)

        cmd = f"cat > {clients_table} <<'JSON_EOF'\n{new_json}\nJSON_EOF\n"
        escaped_cmd = shlex.quote(cmd)
        assert self._conn is not None
        # Запускаем одноразовую команду через docker exec
        result = await self._conn.run(
            f"docker exec -i {self.container} sh -c {escaped_cmd}"
        )

        if result.exit_status == 0:
            logger.success("clientsTable успешно обновлён")
            return True
        else:
            logger.error(f"Ошибка записи clientsTable: {result.stderr}")
            return False

    async def add_new_user_gen_config(self, file_name: str) -> None:
        """Добавляет нового пользователя и генерирует конфигурационный файл.

        Args:
            file_name (str): Имя файла конфигурации.

        """
        if not await self.check_container():
            return
        private_key = await self.generate_private_key()
        pub_key = await self.generate_public_key()
        pub_server_key = await self.get_public_server_key()
        correct_ip = await self.get_correct_ip()
        psk = await self.get_psk_key()

        if (
            private_key is None
            or pub_key is None
            or pub_server_key is None
            or correct_ip is None
            or psk is None
        ):
            logger.bind(user=self.username).error(
                "Не удалось получить все данные для нового пользователя"
            )
            return
        stdout = await self.add_user_in_config(pub_key, correct_ip, psk)
        if stdout == "OK":
            logger.bind(user=self.username).success("Новый конфиг добавлен в wg0.conf")
        else:
            logger.bind(user=self.username).error(
                f"Ошибка при добавлении новой записи: {stdout}"
            )
        user_name = f"{file_name.rsplit('.', 1)[0]}_{random.randint(1, 1000)}"
        await self.add_to_clients_table(pub_key, user_name)

        if await self.save_wg_config(
            file_name, correct_ip, private_key, pub_server_key, psk
        ):
            logger.bind(user=self.username).success(f"Создан файл конфиг: {file_name}")
        else:
            logger.bind(user=self.username).error(
                "Произошла ошибка при создании файла конфига"
            )

    async def close(self) -> None:
        """Закрывает shell-сессию и соединение."""
        if self._process is not None:
            self._process.stdin.write("exit\n")
            await self._process.stdin.drain()
            self._process = None

        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            logger.bind(user=self.username).debug("AsyncSSH: соединение закрыто")
            self._conn = None

    async def __aenter__(self) -> "AsyncSSHClient":
        """Открывает соединение в асинхронном контекстном менеджере.

        Returns
           AsyncSSHClient: Текущий экземпляр клиента.

        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Закрывает соединение в асинхронном контекстном менеджере."""
        await self.close()


if __name__ == "__main__":
    """Пример использования AsyncSSHClient."""
    key_path = (
        Path().home() / ".ssh" / "test_vpn"
    )  # Укажи путь к своему приватному ключу

    async def main() -> None:
        """Пример использования AsyncSSHClient."""
        async with AsyncSSHClient(
            host="help-blocks.ru",
            username="vpn_user",
            key_filename=key_path.as_posix(),
            known_hosts=None,  # Отключить проверку known_hosts
            config_port=32349,
        ) as ssh_client:
            await ssh_client.add_new_user_gen_config("boris33.conf")
            # await ssh_client.add_to_clients_table("your_public_sssskey_here", "boris123")

    asyncio.run(main())
