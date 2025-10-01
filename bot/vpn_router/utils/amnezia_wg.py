import asyncio
import ipaddress
from pathlib import Path
from types import TracebackType
from typing import AsyncGenerator, List, Optional, Tuple, Type

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
           asyncssh.Error: Ошибка внутри библиотеки ``asyncssh``.

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

        """
        marker = "__EXIT__"
        if self._process is None:
            raise RuntimeError("AsyncSSH: shell-сессия не запущена. Вызови connect()")
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
        self, container: str, commands: List[str]
    ) -> AsyncGenerator[Tuple[str, str, int, str], None]:
        """Выполняет список команд внутри контейнера.

        Args:
            container (str): Имя контейнера.
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
            "cd opt/amnezia/awg/",
            "wg genkey > privetkey",
            "cat privetkey",
        ]
        async for stdout, *_ in self.run_commands_in_container(self.container, cmd):
            if stdout:
                return stdout
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
        async for stdout, *_ in self.run_commands_in_container(self.container, cmd):
            if stdout:
                return stdout
        return None

    async def get_correct_ip(self) -> Optional[str]:
        """Определяет корректный IP-адрес клиента для WireGuard.

        Returns
           Optional[str]: IP-адрес в формате "x.x.x.x/32" или None.

        """
        cmd = [
            "cat wg0.conf | grep 'AllowedIPs =' | tail -n 1 | awk '{print $3}'>lastip",
            "cat lastip",
        ]
        async for stdout, *_ in self.run_commands_in_container(self.container, cmd):
            if stdout:
                ip_correct = ipaddress.ip_address(stdout.rpartition("/")[0]) + 1
                return f"{ip_correct}/32"
        return None

    async def add_user_config(self, public_key: str, correct_ip: str) -> Optional[str]:
        """Добавляет конфигурацию пользователя в `wg0.conf`.

        Args:
            public_key (str): Публичный ключ клиента.
            correct_ip (str): IP-адрес клиента.

        Returns
            Optional[str]: Ответ от контейнера или None.

        """
        cmd = [
            'echo " " >> wg0.conf',
            'echo "[Peer]" >> wg0.conf',
            f'echo "PublicKey = {public_key}" >> wg0.conf',
            'echo "PresharedKey = $(cat wireguard_psk.key)" >> wg0.conf',
            f'echo "AllowedIPs = {correct_ip}" >> wg0.conf',
            "echo OK",
        ]
        async for stdout, *_ in self.run_commands_in_container(self.container, cmd):
            if stdout:
                return stdout
        return None

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
        ) as ssh_client:
            # print(await ssh_client.check_container())
            if await ssh_client.check_container():
                print(f"PRIVATE_KEY: {await ssh_client.generate_private_key()}")
                # print(f"PUBLIC_KEY: {await ssh_client.generate_public_key()}")
                # print(f"CORRECT_IP: {await ssh_client.get_correct_ip()}")

                pub_key = await ssh_client.generate_public_key()
                correct_ip = await ssh_client.get_correct_ip()
                if pub_key and correct_ip:
                    print(
                        f"ADD_USER: {await ssh_client.add_user_config(pub_key, correct_ip)}"
                    )
            # cmd1 = await ssh_client.write_single_cmd("whoami")
            # cmd2 = await ssh_client.write_single_cmd("cd opt/amnezia/awg/")
            #
            # print("STDOUT:\n" + cmd1[0])
            # print("STDDERR:\n" + cmd1[1])
            # print("EXITCODE:\n" + str(cmd1[2]))
            # print("CMD:\n" + cmd1[3])
            # print('-' * 40)
            #
            # print("STDOUT:\n" + cmd2[0])
            # print("STDDERR:\n" + cmd2[1])
            # print("EXITCODE:\n" + str(cmd2[2]))
            # print("CMD:\n" + cmd2[3])
            # print('-' * 40)
            #
            # input()
            #
            # commands2 = [
            #     "whoami",
            #     "cd opt/amnezia/awg/",
            #     "wg genkey > privetkey",
            #     "cat privetkey",
            #     "cat privetkey | wg pubkey > publickey",
            #     "cat publickey",
            #     # "cat wg0.conf | grep 'AllowedIPs =' | tail -n 1 | awk '{print $3}'>lastip",
            #     # "cat lastip",
            #     # 'echo " " >> wg0.conf',
            #     # 'echo "[Peer]" >> wg0.conf',
            #     # 'echo "PublicKey = $(cat publickey)" >> wg0.conf',
            #     # 'echo "PresharedKey = $(cat wireguard_psk.key)" >> wg0.conf',
            #     # f'echo "AllowedIPs = $(cat {correct_ip})" >> wg0.conf',
            #     # "rm privetkey publickey lastip",
            # ]
            # result = {}
            #
            # async for stdout, stderr, exit_code, cmd in ssh_client.run_commands_in_container("amnezia-awg",
            #                                                                                  commands2):
            #     print(f"$ {cmd} (exit {exit_code})")
            #     print("stdout:\n", stdout)
            #     result[cmd] = stdout
            #     if stderr:
            #         print("stderr:\n", stderr)
            #     print("-" * 40)
            # pprint(result)

    asyncio.run(main())
