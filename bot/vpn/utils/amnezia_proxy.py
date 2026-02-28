import asyncio
import shlex
from collections.abc import AsyncGenerator
from types import TracebackType

import asyncssh
from loguru import logger

from bot.config import settings_bot
from bot.vpn.utils.amnezia_exceptions import AmneziaError, AmneziaSSHError
from bot.vpn.utils.amnezia_wg import CONNECT_TIMEOUT, USE_LOCAL


class AsyncDockerSSHClient:
    def __init__(
        self,
        host: str = "localhost",
        username: str | None = None,
        port: int = 22,
        known_hosts: str | None = None,
        container: str = "amnezia-awg",
        use_local: bool = USE_LOCAL,
    ) -> None:
        self.container = container
        self.use_local = True
        if not use_local:
            if username is None:
                raise AmneziaError(message="Username обязательное поле")
        self.host = host
        self.username = username
        self.port = port
        self.known_hosts = known_hosts

        self._conn: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess[str] | None = None

    async def connect(self) -> None:
        """Устанавливает SSH-соединение и открывает shell-сессию.

        Raises
           OSError: Ошибка на уровне сокета или ОС.
           Asyncssh.Error: Ошибка внутри библиотеки ``asyncssh``.

        """
        if self.use_local:
            return

        if self._conn is not None:
            logger.bind(user=self.username).debug("AsyncSSH: уже подключён")
            return

        try:
            self._conn = await asyncio.wait_for(
                asyncssh.connect(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    known_hosts=self.known_hosts,
                    agent_forwarding=True,
                ),
                timeout=CONNECT_TIMEOUT,
            )
            self._process = await asyncio.wait_for(
                self._conn.create_process(f"docker exec -i {self.container} sh;\n"),
                timeout=CONNECT_TIMEOUT,
            )
            logger.bind(user=self.username).debug(
                f"AsyncSSH: подключение и shell-сессия установлены к {self.host}"
            )
        except TimeoutError:
            logger.bind(user=self.username).error(
                f"AsyncSSH: таймаут подключения к {self.host}"
            )
            raise AmneziaSSHError(
                message=f"SSH timeout при подключении к {self.host}:{self.port}"
            )

        except (OSError, asyncssh.Error) as exc:
            logger.bind(user=self.username).error(
                f"AsyncSSH: ошибка подключения: {exc}"
            )
            raise

    async def write_single_cmd(self, cmd: str) -> tuple[str, str, int, str]:
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
        if self.use_local:
            full_cmd = f"docker exec -i {self.container} sh -c {shlex.quote(cmd)}"
            process = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            return (
                stdout.decode().strip(),
                stderr.decode().strip(),
                process.returncode,
                cmd,
            )
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
        except TimeoutError:
            pass

        return stdout.strip(), stderr.strip(), exit_code, cmd

    async def run_commands_in_container(
        self, commands: list[str]
    ) -> AsyncGenerator[tuple[str, str, int, str], None]:
        """Выполняет список команд внутри контейнера.

        Args:
            commands (List[str]): Список команд для выполнения.

        Yields
            Tuple[str, str, int, str]: stdout, stderr, exit_code, команда.

        """
        for cmd in commands:
            stdout, stderr, exit_code, cmd = await self.write_single_cmd(cmd)
            yield stdout, stderr, exit_code, cmd

    async def restart_container(self) -> bool:
        """Перезапускает Docker-контейнер.

        Returns
            bool: True если контейнер успешно перезапущен.

        """
        cmd = f"/usr/bin/docker restart {self.container}"

        if self.use_local:
            stdout, stderr, code, _ = await self.write_single_cmd(cmd)
        else:
            assert self._conn is not None
            result = await self._conn.run(cmd)
            stdout, stderr, code = (
                result.stdout,
                result.stderr,
                result.exit_status,
            )

        if code == 0:
            logger.success(f"Контейнер {self.container} успешно перезапущен")
            return True

        raise AmneziaSSHError(
            message="Ошибка при перезапуске контейнера",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )

    async def close(self) -> None:
        """Закрывает shell-сессию и соединение."""
        if self._process is not None:
            try:
                self._process.close()  # Закрываем процесс
                await self._process.wait_closed()  # Ждём завершения
            except (BrokenPipeError, OSError):
                logger.debug("Shell-сессия уже закрыта")

        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            logger.bind(user=self.username).debug("AsyncSSH: соединение закрыто")
            self._conn = None

    async def __aenter__(self) -> "AsyncDockerSSHClient":
        """Открывает соединение в асинхронном контекстном менеджере.

        Returns
           AsyncSSHClient: Текущий экземпляр клиента.

        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Закрывает соединение в асинхронном контекстном менеджере."""
        await self.close()


class AmneziaProxy:
    """Сервис управления пользователями 3proxy внутри Docker-контейнера.

    Работает через AsyncDockerSSHClient и выполняет команды
    непосредственно внутри контейнера.
    """

    CONF_DIR = "/usr/local/3proxy/conf"
    USER_FILE = "users.txt"

    def __init__(self, client: AsyncDockerSSHClient, port: str = "40711") -> None:
        self.client = client
        self.port = port

    async def _check_container(self) -> bool:
        """Проверяет доступность контейнера.

        Returns
           bool: True, если контейнер доступен и команда `whoami` вернула "root".

        Raises
            AmneziaSSHError: Если контейнер недоступен или команда не вернула "root".

        """
        stdout, stderr, _, cmd = await self.client.write_single_cmd("whoami")
        if stdout == "root":
            logger.debug("Проверка контейнера прошла успешно")
            return True
        else:
            raise AmneziaSSHError(
                f"Контейнер {self.client.container} недоступен или не запущен",
                cmd=cmd,
                stdout=stdout,
                stderr=stderr,
            )

    def _build_tg_link(self, username: str, password: str) -> str:
        """Формирует Telegram socks-ссылку."""
        return (
            f"https://t.me/socks?"
            f"server={self.client.host}"
            f"&port={self.port}"
            f"&user={username}"
            f"&pass={password}"
        )

    async def add_user(self, username: str, password: str) -> str:
        """Добавляет пользователя в users.txt 3proxy.

        Строка добавляется в формате:
            username:CL:password

        Args:
            username: Имя пользователя (без символа ':').
            password: Пароль пользователя (без символа ':').

        Returns
            str: если пользователь успешно добавлен ссылку на прокси

        Raises
            ValueError: Если username или password содержат ':'.
            AmneziaSSHError: Если произошла ошибка при записи в файл.

        """

        if ":" in username or ":" in password:
            raise ValueError("Username и password не должны содержать ':'")

        user_file = f"{self.CONF_DIR}/{self.USER_FILE}"
        line = f"{username}:CL:{password}"

        check_cmd = f"grep '^{shlex.quote(username)}:' {user_file}"
        stdout, _, exit_code, _ = await self.client.write_single_cmd(check_cmd)

        if exit_code == 0:
            try:
                existing_password = stdout.strip().split(":")[2]
            except (IndexError, ValueError):
                raise AmneziaSSHError(
                    message="Некорректный формат строки пользователя",
                    cmd=check_cmd,
                    stdout=stdout,
                    stderr="",
                )

            logger.info(f"Пользователь {username} уже существует")
            return self._build_tg_link(username, existing_password)

        append_cmd = f"echo {shlex.quote(line)} >> {user_file}"
        stdout, stderr, code, cmd = await self.client.write_single_cmd(append_cmd)
        if code == 0:
            logger.success(f"Пользователь {username} успешно добавлен")
            await self.client.restart_container()
            return self._build_tg_link(username, password)

        raise AmneziaSSHError(
            message="Ошибка при добавлении пользователя",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )

    async def delete_user(self, username: str) -> bool:
        """Удаляет пользователя из users.txt по имени.

        Удаляется строка, начинающаяся с:
            username:

        Args:
            username: Имя пользователя для удаления.

        Returns
            True: если пользователь успешно удалён.
            False: если пользователь не найден.

        Raises
            ValueError: Если username содержит ':'.
            AmneziaSSHError: Если произошла ошибка при модификации файла.

        """

        if ":" in username:
            raise ValueError("Username не должен содержать ':'")

        user_file = f"{self.CONF_DIR}/{self.USER_FILE}"

        check_cmd = f"grep -q '^{shlex.quote(username)}:' {user_file}"
        _, _, exit_code, _ = await self.client.write_single_cmd(check_cmd)

        if exit_code != 0:
            logger.warning("Пользователь не найден")
            return False

        delete_cmd = f"sed -i '/^{shlex.quote(username)}:/d' {user_file}"
        stdout, stderr, code, cmd = await self.client.write_single_cmd(delete_cmd)

        if code == 0:
            logger.success(f"Пользователь {username} удалён")
            await self.client.restart_container()
            return True

        raise AmneziaSSHError(
            message="Ошибка при удалении пользователя",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )

    async def reload_3proxy(self) -> bool:
        """Перезагружает процесс 3proxy без остановки контейнера.

        Отправляет сигнал HUP процессу 3proxy для перечитывания конфигурации.

        Returns
            True: если reload выполнен успешно.

        Raises
            AmneziaSSHError: Если сигнал не был отправлен или команда завершилась с ошибкой.

        """
        cmd = "pkill -HUP 3proxy"
        stdout, stderr, code, _ = await self.client.write_single_cmd(cmd)

        if code == 0:
            logger.success("3proxy успешно перезагружен")
            return True

        raise AmneziaSSHError(
            message="Ошибка при reload 3proxy",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )


if __name__ == "__main__":

    async def main() -> None:
        async with AsyncDockerSSHClient(
            host=settings_bot.vpn_host,
            username=settings_bot.vpn_username,
            container=settings_bot.vpn_proxy,
        ) as client:
            await client.connect()
            proxy = AmneziaProxy(client=client, port=settings_bot.proxy_port)
            await proxy._check_container()
            await proxy.add_user(username="user1", password="password")
            # await proxy.delete_user(username="user1")
            await proxy.reload_3proxy()

    asyncio.run(main())
