import asyncio
import ipaddress
import json
import shlex
import uuid
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, AsyncGenerator, List, Optional, Tuple, Type

import aiofiles  # type: ignore
import asyncssh

from bot.config import logger
from bot.vpn_router.utils.amnezia_exceptions import (
    AmneziaConfigError,
    AmneziaError,
    AmneziaSSHError,
)


class AsyncSSHClientWG:
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
    WG_CLIENTS_TABLE = f"{WG_DIR}/clientsTable"

    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        key_filename: Optional[str] = None,
        known_hosts: Optional[str] = None,
        container: str = "amnezia-awg",
    ) -> None:
        self.host = host
        self.username = username
        self.port = port
        self.key_filename = key_filename
        self.known_hosts = known_hosts
        self.container = container
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
            raise AmneziaSSHError(
                "AsyncSSH: shell-сессия не запущена. Вызови connect()"
            )
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

    async def _check_container(self) -> bool:
        """Проверяет доступность контейнера.

        Returns
           bool: True, если контейнер доступен и команда `whoami` вернула "root".

        Raises
            AmneziaSSHError: Если контейнер недоступен или команда не вернула "root".

        """
        stdout, stderr, _, cmd = await self.write_single_cmd("whoami")
        if stdout == "root":
            logger.debug("Проверка контейнера прошла успешно")
            return True
        else:
            raise AmneziaSSHError(
                f"Контейнер {self.container} недоступен или не запущен",
                cmd=cmd,
                stdout=stdout,
                stderr=stderr,
            )

    async def _generate_private_key(self) -> Optional[str]:
        """Генерирует приватный ключ в контейнере.

        Returns
           Optional[str]: Приватный ключ или None, если не удалось получить.

        Raises
            AmneziaSSHError: Если произошла ошибка при генерации ключа.

        """
        cmd = [
            f"cd {self.WG_DIR}",
            "wg genkey > privatekey",
            "cat privatekey",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                return stdout
            elif stderr:
                if "Warning" in stderr:
                    logger.bind(user=self.username).warning(
                        f"Предупреждение при генерации ключа, можно продолжать: {stderr}"
                    )
                else:
                    raise AmneziaSSHError(
                        message=f"Ошибка при генерации "
                        f"приватного ключа "
                        f"пользователя: {stderr}",
                        cmd=";".join(cmd),
                        stderr=stderr,
                    )
        return None

    async def _generate_public_key(self) -> Optional[str]:
        """Генерирует публичный ключ из приватного.

        Returns
            Optional[str]: Публичный ключ или None, если не удалось получить.

        Raises
            AmneziaSSHError: Если произошла ошибка при генерации ключа.

        """
        cmd = [
            "cat privatekey | wg pubkey > publickey",
            "cat publickey",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                return stdout
            elif stderr:
                raise AmneziaSSHError(
                    message=f"Ошибка при генерации публичного ключа: {stderr}",
                    cmd=";".join(cmd),
                    stderr=stderr,
                )
        return None

    async def _get_vpn_params_config(self) -> tuple[dict[Any, Any], int] | None:
        """Получает индивидуальные данные для подключения VPN и порт контейнера.

        Считывает файл конфигурации WireGuard (`wg0.conf`) внутри контейнера
        и возвращает словарь с параметрами интерфейса `[Interface]` и порт `ListenPort`.

        Returns
            Optional[Tuple[Dict[str, Any], int]]:
                Кортеж из:
                - params (dict[str, Any]): Параметры интерфейса WireGuard (например, Jc, Jmin, H1 и т.д.).
                - listen_port (int): Порт прослушивания интерфейса.
                Возвращает None, если не удалось получить данные.

        Raises
            AmneziaConfigError: Если не удалось прочитать конфигурацию или получен stderr.

        """
        cmd = f"cat {self.WG_CONF}"
        stdout, stderr, *_ = await self.write_single_cmd(cmd)
        if stdout:
            in_interface = False
            params = {}
            listen_port = 1

            for line in stdout.splitlines():
                line = line.strip()
                if line == "[Interface]":
                    in_interface = True
                    continue
                elif line.startswith("[Peer]"):
                    break
                if in_interface and "=" in line:
                    key, value = map(str.strip, line.split("=", 1))
                    if key in {
                        "Jc",
                        "Jmin",
                        "Jmax",
                        "S1",
                        "S2",
                        "H1",
                        "H2",
                        "H3",
                        "H4",
                    }:
                        params[key] = value
                    elif key in {"ListenPort"}:
                        try:
                            listen_port = int(value)
                        except ValueError:
                            listen_port = 1
            return params, listen_port
        elif stderr:
            raise AmneziaConfigError(
                message=f"Ошибка получении конфига параметров VPN: {stderr}",
                file=self.WG_CONF,
                stderr=stderr,
            )

        return None

    async def _get_correct_ip(self) -> Optional[str]:
        """Определяет корректный IP-адрес клиента для WireGuard.

        Returns
           Optional[str]: IP-адрес в формате "x.x.x.x/32" или None.

        Raises
            ValueError: Если полученный IP некорректен.
            AmneziaConfigError: Если произошла ошибка при получении IP.

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
                    raise
            elif stderr:
                raise AmneziaConfigError(
                    message=f"Ошибка при получении IP: {stderr}",
                    file=self.WG_CONF,
                    stderr=stderr,
                )
        return None

    async def _get_psk_key(self) -> Optional[str]:
        """Определяет preshared_key от  WireGuard.

        Returns
           Optional[str]: preshared_key или None.

        Raises
            AmnweziaConfigError: Если произошла ошибка при получении PSK.

        """
        psk_key_file = f"{self.WG_DIR}/wireguard_psk.key"
        stdout, stderr, *_ = await self.write_single_cmd(f"cat {psk_key_file}")
        if stdout:
            return stdout
        elif stderr:
            raise AmneziaConfigError(
                message=f"Ошибка при получении PSK: {stderr}",
                file=psk_key_file,
                stderr=stderr,
            )
        return None

    async def _get_public_server_key(self) -> Optional[str]:
        """Определяет public_key от  WireGuard сервера.

        Returns
           Optional[str]: public_key или None.

        Raises
            AmneziaConfigError: Если произошла ошибка при получении public key сервера.

        """
        stdout, stderr, *_ = await self.write_single_cmd(
            "cat wireguard_server_public_key.key"
        )
        if stdout:
            return stdout
        elif stderr:
            raise AmneziaConfigError(
                message=f"Ошибка при получении public key сервера: {stderr}",
                file="wireguard_server_public_key.key",
                stderr=stderr,
            )
        return None

    async def _add_user_in_config(
        self, public_server_key: str, correct_ip: str, psk_key: str
    ) -> Optional[str]:
        """Добавляет конфигурацию пользователя в `wg0.conf`.

        Args:
            public_server_key (str): Публичный ключ клиента.
            correct_ip (str): IP-адрес клиента.
            psk_key (str): preshared key сервера.

        Returns
            Optional[str]: "OK", если успешно, иначе None.

        Raises
            AmneziaConfigError: Если произошла ошибка при добавлении нового пользователя.

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
            elif stderr:
                raise AmneziaConfigError(
                    message=f"Ошибка при добавлении нового пользователя: {stderr}",
                    file=self.WG_CONF,
                    stderr=stderr,
                )
        return None

    async def _generate_wg_config(
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
        vpn_config = await self._get_vpn_params_config()
        assert vpn_config is not None, "Не удалось получить параметры VPN"
        vpn_params, listen_port = vpn_config
        interface_data = {
            "Address": new_ip,
            "DNS": "1.1.1.1, 1.0.0.1",
            "PrivateKey": private_key,
        }
        interface_data.update(vpn_params)
        peer_data = {
            "PublicKey": pub_server_key,
            "PresharedKey": preshared_key,
            "AllowedIPs": "0.0.0.0/0, ::/0",
            "Endpoint": f"{self.host}:{listen_port}",
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

    async def _reboot_interface(self) -> Optional[bool]:
        """Перезапускает интерфейс WireGuard внутри контейнера.

        Выполняет команды `wg-quick down` и `wg-quick up` через SSH внутри контейнера.
        Если команды прошли успешно, возвращается True. Если интерфейс не удалось
        перезапустить, возвращается None.

        Returns
            Optional[bool]: True, если интерфейс успешно перезапущен, иначе None.

        Raises
            AmneziaSSHError: Если произошла ошибка при выполнении команд перезапуска интерфейса.

        """
        cmd = [f"wg-quick down {self.WG_CONF}", f"wg-quick up {self.WG_CONF}"]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                logger.bind(user=self.username).success(
                    f"Интерфейс выключен/включен:\n{stdout}"
                )
                return True
            if stderr:
                if "Warning" in stderr:
                    logger.bind(user=self.username).warning(
                        f"Предупреждение при перезапуске интерфейса, можно продолжать: {stderr}"
                    )
                else:
                    raise AmneziaSSHError(
                        message="Ошибка при перезапуске интерфейса",
                        cmd=";".join(cmd),
                        stderr=stderr,
                    )
        return None

    async def _save_wg_config(
        self,
        filename: str,
        new_ip: str,
        private_key: str,
        pub_server_key: str,
        preshared_key: str,
    ) -> bool:
        """Создает и сохраняет пользовательский конфиг.

        Args:
            filename (str): Название файла конфигурации.
            new_ip (str): IP-адрес пользователя.
            private_key (str): Приватный ключ пользователя.
            pub_server_key (str): Публичный ключ сервера.
            preshared_key (str): PSK ключ сервера.

        Returns
            bool: True, если конфиг создан

        """
        config_text = await self._generate_wg_config(
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

        return True

    async def _add_to_clients_table(self, public_key: str, client_name: str) -> bool:
        """Добавляет запись в clientsTable Amnezia.

        Args:
            public_key (str): Публичный ключ клиента (clientId).
            client_name (str): Имя клиента (userData.clientName).

        Returns
            bool: True если запись добавлена.

        Raises
            AmneziaConfigError: Если произошла ошибка при добавлении записи в clientsTable.
            JSONDecodeError: Если JSON в clientsTable некорректен.

        """
        stdout, stderr, code, _ = await self.write_single_cmd(
            f"cat {self.WG_CLIENTS_TABLE}"
        )
        if stderr:
            logger.error(f"Не удалось прочитать clientsTable: {stderr}")
            raise AmneziaConfigError(
                message=f"Ошибка при чтении clientsTable: {stderr}",
                file=self.WG_CLIENTS_TABLE,
                stderr=stderr,
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга clientsTable: {e}")
            raise
        if any(item.get("clientId") == public_key for item in data):
            logger.info("Клиент уже в clientsTable")
            return True

        creation_date = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
        data.append(
            {
                "clientId": public_key,
                "userData": {"clientName": client_name, "creationDate": creation_date},
            }
        )
        new_json = json.dumps(data, indent=4, ensure_ascii=False)

        cmd = f"cat > {self.WG_CLIENTS_TABLE} <<'JSON_EOF'\n{new_json}\nJSON_EOF\n"
        escaped_cmd = shlex.quote(cmd)
        assert self._conn is not None
        result = await self._conn.run(
            f"docker exec -i {self.container} sh -c {escaped_cmd}"
        )
        if result.exit_status == 0:
            logger.success("clientsTable успешно обновлён")
            return True
        else:
            raise AmneziaSSHError(
                "Ошибка при записи clientsTable",
                cmd=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
            )

    async def _delete_temp_files(self) -> None:
        """Удаляет временные файлы ключей внутри контейнера.

        Удаляются файлы `privatekey`, `publickey` и `lastip` в директории WireGuard
        внутри Docker-контейнера. Если возникает ошибка при удалении любого из файлов,
        выбрасывается исключение AmneziaSSHError.

        Raises
            AmneziaSSHError: Если произошла ошибка при удалении временных файлов.

        """
        cmd = [
            f"rm -f {self.WG_DIR}/privatekey",
            f"rm -f {self.WG_DIR}/publickey",
            f"rm -f {self.WG_DIR}/lastip",
        ]
        async for stdout, stderr, *_ in self.run_commands_in_container(cmd):
            if stdout:
                logger.debug(f"Удаление временных файлов: {stdout}")
            if stderr:
                raise AmneziaSSHError(
                    message="Ошибка при удалении временных файлов",
                    cmd=";".join(cmd),
                    stderr=stderr,
                )

    async def add_new_user_gen_config(self, file_name: str) -> None:
        """Добавляет нового пользователя и генерирует конфигурационный файл WireGuard.

        Последовательно выполняются следующие шаги:
            1. Проверяется доступность контейнера.
            2. Генерируется приватный и публичный ключ пользователя.
            3. Получается публичный ключ сервера.
            4. Определяется корректный IP для нового клиента.
            5. Получает Preshared Key (PSK).
            6. Добавляется запись в wg0.conf.
            7. Добавляется запись в clientsTable.
            8. Сохраняется конфигурационный файл пользователя.
            9. Удаляются временные файлы ключей.
            10. Перезапускается интерфейс WireGuard.

        Args:
            file_name (str): Имя файла конфигурации для нового пользователя.

        Raises
            AmneziaError: Если произошла любая ошибка при работе с контейнером,
                ключами, конфигурацией или clientsTable.

        """
        try:
            await self._check_container()

            private_key = await self._generate_private_key()
            pub_key = await self._generate_public_key()
            pub_server_key = await self._get_public_server_key()
            correct_ip = await self._get_correct_ip()
            psk = await self._get_psk_key()
            # Уверяем MyPy, что это точно str
            assert private_key is not None
            assert pub_key is not None
            assert pub_server_key is not None
            assert correct_ip is not None
            assert psk is not None
            stdout = await self._add_user_in_config(pub_key, correct_ip, psk)
            if stdout == "OK":
                logger.bind(user=self.username).success(
                    "Новый конфиг добавлен в wg0.conf"
                )
            user_name = f"{file_name.rsplit('.', 1)[0]}_{uuid.uuid4().hex}"
            client_table = await self._add_to_clients_table(pub_key, user_name)
            if client_table:
                logger.bind(user=self.username).success(
                    "Новый клиент добавлен в clientsTable"
                )
            if await self._save_wg_config(
                file_name, correct_ip, private_key, pub_server_key, psk
            ):
                logger.bind(user=self.username).success(
                    f"Создан файл конфиг: {file_name}"
                )
            await self._delete_temp_files()
            await self._reboot_interface()
        except AmneziaError as e:
            logger.error(e)
            raise

    async def _delete_user_wg0(self, public_key: str) -> bool | None:
        """Удаляет пользователя с указанным публичным ключом из wg0.conf.

        Метод читает файл конфигурации WireGuard, ищет блок `[Peer]` с заданным
        `public_key` и удаляет его вместе с соответствующими строками. Затем
        перезаписывает конфигурацию обратно в файл внутри контейнера.

        Args:
            public_key (str): Публичный ключ пользователя, которого нужно удалить.

        Returns
            Optional[bool]:
                - True: пользователь найден и удалён.
                - False: пользователь с указанным ключом не найден.
                - None: в случае непредвиденной ошибки (редко).

        Raises
            AmneziaSSHError: Если произошла ошибка при записи нового конфигурационного
                файла в контейнер.
            AmneziaConfigError: Если произошла ошибка при чтении конфигурации wg0.conf.

        """
        wg0 = f"cat {self.WG_CONF}"
        stdout, stderr, code, cmd = await self.write_single_cmd(cmd=wg0)
        if stdout:
            out_data = []
            deleted_lines = False
            for line in stdout.splitlines():
                if "Peer" in line and deleted_lines:
                    deleted_lines = False
                elif "Peer" in line and not deleted_lines:
                    continue
                elif "PublicKey" in line and public_key in line:
                    deleted_lines = True
                    continue
                elif "PublicKey" in line and public_key not in line:
                    out_data.append("[Peer]")
                if not deleted_lines:
                    out_data.append(line)
            if len(stdout.splitlines()) != len(out_data):
                logger.info(f"Нашел пользователя с таким ключем в {self.WG_CONF}")
            else:
                logger.warning(
                    f"Пользователь с таким ключем не найден в {self.WG_CONF}"
                )
                return False
            new_conf = "\n".join(out_data)
            cmd = f"cat > {self.WG_CONF} <<'EOF'\n{new_conf}\nEOF\n"
            escaped_cmd = shlex.quote(cmd)
            assert self._conn is not None
            result = await self._conn.run(
                f"docker exec -i {self.container} sh -c {escaped_cmd}"
            )
            if result.exit_status == 0:
                logger.success(f"Пользователь успешно удален из {self.WG_CONF}")
                return True
            else:
                raise AmneziaSSHError(
                    message=f"Ошибка записи wg0.conf: {result.stderr}",
                    cmd=cmd,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

        elif stderr:
            raise AmneziaConfigError(
                message=f"Ошибка при чтении конфига {self.WG_CONF}: {stderr}",
                file=self.WG_CONF,
                stderr=stderr,
            )
        return None

    async def _delete_from_clients_table(
        self,
        public_key: str,
    ) -> bool:
        """Удаляет запись пользователя из clientsTable по публичному ключу.

        Метод читает текущий clientsTable, ищет запись с `clientId`, равным
        `public_key`, и удаляет её. После удаления обновлённый JSON
        перезаписывается обратно в файл внутри контейнера.

        Args:
            public_key (str): Публичный ключ клиента (`clientId`), который нужно удалить.

        Returns
            bool:
                - True, если запись была найдена и удалена.
                - False, если запись с указанным ключом не найдена.

        Raises
            AmneziaConfigError: Если произошла ошибка при чтении clientsTable или
                JSON не удалось распарсить.
            AmneziaSSHError: Если произошла ошибка при записи обновлённого JSON
                обратно в контейнер.

        """
        clients_table = f"{self.WG_DIR}/clientsTable"
        stdout, stderr, code, _ = await self.write_single_cmd(f"cat {clients_table}")
        if stderr:
            logger.error(f"Не удалось прочитать clientsTable: {stderr}")
            raise AmneziaConfigError(
                message=f"Не удалось прочитать {clients_table}: {stderr}",
                file=clients_table,
                stderr=stderr,
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга clientsTable: {e}")
            raise
        new_data = [item for item in data if item.get("clientId") != public_key]

        if len(new_data) < len(data):
            logger.info(f"Нашел клиента с таким ключем в {clients_table}")
        else:
            logger.warning(f"Клиент с таким ключем не найден в {clients_table}")
            return False

        new_json = json.dumps(new_data, indent=4, ensure_ascii=False)

        cmd = f"cat > {clients_table} <<'JSON_EOF'\n{new_json}\nJSON_EOF\n"
        escaped_cmd = shlex.quote(cmd)
        assert self._conn is not None
        result = await self._conn.run(
            f"docker exec -i {self.container} sh -c {escaped_cmd}"
        )

        if result.exit_status == 0:
            logger.success(f"Ключ успешно удален из {clients_table}")
            return True
        else:
            raise AmneziaSSHError(
                message=f"Ошибка при удалении ключа из {clients_table}",
                cmd=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
            )

    async def full_delete_user(self, public_key: str) -> bool | None:
        """Полностью удаляет пользователя из конфигурации WireGuard и clientsTable.

        Метод пытается удалить пользователя с заданным публичным ключом
        из конфигурационного файла `wg0.conf` и из таблицы клиентов.
        После успешного удаления интерфейс WireGuard перезапускается.

        Args:
            public_key (str): Публичный ключ клиента (`clientId`), который нужно удалить.

        Returns
            bool:
                - True, если пользователь был успешно удалён и интерфейс перезапущен.
                - False, если произошла ошибка удаления или пользователь не найден.

        Raises
            AmneziaError: В случае ошибок при удалении из конфигурации или таблицы клиентов.

        """
        try:
            deleted_from_config = await self._delete_user_wg0(public_key)
            deleted_from_table = await self._delete_from_clients_table(public_key)
            if deleted_from_table and deleted_from_config:
                logger.success(
                    "Пользователь полностью удален из конфигурации и таблицы клиентов."
                )
                return await self._reboot_interface()
            else:
                return False
        except AmneziaError as e:
            logger.error(e)
            return False

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

    async def __aenter__(self) -> "AsyncSSHClientWG":
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
    key_path = Path().home() / ".ssh" / "test_vpn"

    async def main() -> None:
        """Пример использования AsyncSSHClient."""
        async with AsyncSSHClientWG(
            host="help-blocks.ru",
            username="vpn_user",
            key_filename=key_path.as_posix(),
            known_hosts=None,  # Отключить проверку known_hosts
            container="amnezia-awg",
        ) as ssh_client:
            # await ssh_client.add_new_user_gen_config("boris789.conf")
            # await ssh_client.full_delete_user(
            #     "EbXGP3l+Mz6q6huezEfmNr5AKjLcVBDfy+wfAQ2tFHY="
            # )
            await ssh_client.connect()

    asyncio.run(main())
