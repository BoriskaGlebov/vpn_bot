import asyncio
from pathlib import Path
from types import TracebackType
from typing import AsyncGenerator, List, Optional, Tuple, Type

import asyncssh

from bot.config import logger


class AsyncSSHClient:
    """Асинхронный SSH-клиент с поддержкой контекстного менеджера.

    Args:
        host (str): Адрес сервера (IP или DNS).
        username (str): Имя пользователя.
        port (int, optional): SSH-порт. По умолчанию ``22``.
        key_filename (Optional[str], optional): Путь к приватному ключу.
            Если ``None`` (по умолчанию), ищет ключи в ``~/.ssh``.
        known_hosts (Optional[str], optional): Путь к файлу ``known_hosts``.
            Если ``None``, проверка отключается.

    """

    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        key_filename: Optional[str] = None,
        known_hosts: Optional[str] = None,
    ) -> None:
        self.host = host
        self.username = username
        self.port = port
        self.key_filename = key_filename
        self.known_hosts = known_hosts
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
            self._process = await self._conn.create_process()
            logger.bind(user=self.username).debug(
                f"AsyncSSH: подключение и shell-сессия установлены к {self.host}"
            )
        except (OSError, asyncssh.Error) as exc:
            logger.bind(user=self.username).error(
                f"AsyncSSH: ошибка подключения: {exc}"
            )
            raise

    async def run_commands_stream(
        self, commands: List[str]
    ) -> AsyncGenerator[Tuple[str, str, int, str], None]:
        """Выполняет команды последовательно в одной shell-сессии.

        Args:
        commands (List[str]): Список команд для выполнения.

        Yields
        Tuple[str, str, int, str]: Кортеж вида
        ``(stdout, stderr, exit_code, команда)``.

        Raises
        RuntimeError: Если shell-сессия не запущена.

        """
        if self._process is None:
            raise RuntimeError("AsyncSSH: shell-сессия не запущена. Вызови connect()")
        start_marker = (True, "echo __START__; ", "__START__")
        for cmd in commands:
            marker = "__EXIT__"
            full_cmd = (
                f"{start_marker[1] if start_marker[0] else ''}{cmd}; echo {marker}:$?\n"
            )
            # отправляем команду
            self._process.stdin.write(full_cmd)
            await self._process.stdin.drain()
            # читаем stdout до маркера
            output = await self._process.stdout.readuntil(marker)
            stdout, _, exit_info = output.split(start_marker[2])[1].rpartition("\n")
            try:
                exit_code = int(exit_info.split(":")[-1])
            except ValueError:
                exit_code = 0

            # читаем stderr (неблокирующее чтение)
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
                pass  # поток пустой, продолжаем

            yield stdout.strip(), stderr.strip(), exit_code, cmd

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
        """Открывает соединение в асинхронном контекстном менеджере."""
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

    print(key_path.as_posix())
    print(key_path.exists())

    async def main() -> None:
        """Пример использования AsyncSSHClient."""
        async with AsyncSSHClient(
            host="help-blocks.ru",
            username="vpn_user",
            key_filename=key_path.as_posix(),
            known_hosts=None,  # Отключить проверку known_hosts
        ) as ssh_client:
            commands = [
                "whoami",
                "docker exec amnezia-awg ls",
                "ls",
            ]
            async for stdout, stderr, exit_code, cmd in ssh_client.run_commands_stream(
                commands
            ):
                print(f"$ {cmd} (exit {exit_code})")
                print("stdout:\n", stdout)
                if stderr:
                    print("stderr:\n", stderr)
                print("-" * 40)

    asyncio.run(main())
