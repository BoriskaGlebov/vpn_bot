"""Общий SSH/Docker-транспорт для выполнения команд в контейнере или на хосте.

Использовался параллельно и почти дословно продублированным в `amnezia_wg.py`
(WG-клиент) и в клиенте для Docker-хоста, и копии успели разойтись в деталях
обработки ошибок (см. аудит, issue #221). Здесь — единая точка этой логики;
специфика каждого клиента (конфиги WireGuard, перезапуск контейнера) остаётся
в своих модулях (`amnezia_wg.py`, `docker_ssh_client.py`).
"""

import asyncio
import shlex
from collections.abc import AsyncGenerator
from types import TracebackType
from typing import Self

import asyncssh

from bot.core.config import logger, settings_bot
from bot.vpn.utils.amnezia_exceptions import AmneziaError, AmneziaSSHError

CONNECT_TIMEOUT = settings_bot.core.common_timeout


def _decode_stream(stream: str | bytes | None) -> str:
    """Приводит stdout/stderr результата asyncssh к строке.

    Args:
        stream (str | bytes | None): Поток вывода команды.

    Returns
        str: Декодированный вывод, либо пустая строка, если потока нет.

    """
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode()


class AsyncContainerShellClient:
    """Асинхронный клиент для выполнения команд в Docker-контейнере или на хосте.

    Поддерживает два независимых переключателя:
        - `use_local` — команды идут через локальный `docker exec`/subprocess
          (True) либо по SSH (False);
        - `in_container` — команды выполняются внутри Docker-контейнера,
          оборачиваясь в `docker exec -i <container> ...` (True), либо
          напрямую на хосте, которым управляет `host`/SSH-соединение (False).
          Нужен, например, для MTProto: `docker logs`/`docker restart`
          выполняются на хосте, а не внутри целевого контейнера.

    Args:
        host (str): Адрес сервера (IP или DNS).
        username (str | None): Имя пользователя при подключении по SSH.
        port (int): SSH-порт.
        known_hosts (str | None): Путь к файлу known_hosts. Если None,
            проверка отключается.
        container (str): Имя Docker-контейнера, в котором выполняются команды.
            Не используется при `in_container=False`.
        use_local (bool): True — через локальный `docker exec`, False — по SSH.
        in_container (bool): True — команды выполняются внутри `container`
            (persistent shell-сессия через `docker exec -i ... sh`), False —
            напрямую на хосте (локальный subprocess либо одноразовый
            `SSHClientConnection.run`, без постоянной сессии).

    Attributes
        _conn (asyncssh.SSHClientConnection | None): SSH-соединение.
        _process (asyncssh.SSHClientProcess[str] | None):
            Открытая shell-сессия внутри контейнера (только при `in_container=True`).

    """

    def __init__(
        self,
        host: str = "localhost",
        username: str | None = None,
        port: int = 22,
        known_hosts: str | None = None,
        container: str = "amnezia-awg",
        use_local: bool = True,
        in_container: bool = True,
    ) -> None:
        self.container = container
        self.use_local = use_local
        self.in_container = in_container
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
            if self.in_container:
                self._process = await asyncio.wait_for(
                    self._conn.create_process(f"docker exec -i {self.container} sh;\n"),
                    timeout=CONNECT_TIMEOUT,
                )
            logger.bind(user=self.username).debug(
                f"AsyncSSH: подключение установлено к {self.host}"
                + (" (shell-сессия в контейнере)" if self.in_container else "")
            )
        except TimeoutError as e:
            logger.bind(user=self.username).error(
                f"AsyncSSH: таймаут подключения к {self.host}"
            )
            raise AmneziaSSHError(
                message=f"SSH timeout при подключении к {self.host}:{self.port}"
            ) from e

        except (OSError, asyncssh.Error) as exc:
            logger.bind(user=self.username).error(
                f"AsyncSSH: ошибка подключения: {exc}"
            )
            raise AmneziaSSHError(
                message=f"AsyncSSH: ошибка подключения: {exc}"
            ) from exc

    async def write_single_cmd(self, cmd: str) -> tuple[str, str, int | None, str]:
        """Выполняет одну команду в контейнере (`in_container=True`) либо на хосте.

        Args:
            cmd (str): Команда для выполнения.

        Returns
            Tuple[str, str, int, str]: Кортеж:
                - stdout (str): Стандартный вывод команды.
                - stderr (str): Стандартный поток ошибок.
                - exit_code (int): Код возврата команды.
                - cmd (str): Выполненная команда.

        Raises
            AmneziaSSHError: Если shell-сессия/SSH-соединение не запущены,
                соединение оборвалось во время чтения вывода команды, либо код
                возврата не удалось разобрать.

        """
        if self.use_local:
            full_cmd = (
                f"docker exec -i {self.container} sh -c {shlex.quote(cmd)}"
                if self.in_container
                else cmd
            )
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
        if not self.in_container:
            if self._conn is None:
                raise AmneziaSSHError(
                    "AsyncSSH: соединение не установлено. Вызови connect()"
                )
            result = await self._conn.run(cmd)
            return (
                _decode_stream(result.stdout).strip(),
                _decode_stream(result.stderr).strip(),
                result.exit_status,
                cmd,
            )
        if self._process is None:
            raise AmneziaSSHError(
                "AsyncSSH: shell-сессия не запущена. Вызови connect()"
            )
        marker = "__EXIT__"
        self._process.stdin.write(f"{cmd}; echo {marker}:$?\n")
        await self._process.stdin.drain()
        try:
            output = await self._process.stdout.readuntil("\n")
            while marker not in output:
                output += await self._process.stdout.readuntil("\n")
        except asyncio.IncompleteReadError as e:
            if not e.partial:
                raise AmneziaSSHError(
                    "AsyncSSH: соединение закрыто при чтении stdout"
                ) from e
            raise
        stdout_text, _, exit_info = output.rpartition("__EXIT__")
        try:
            exit_code = int(exit_info.split(":")[-1])
        except ValueError as e:
            # Неразборчивый код возврата — сбой протокола общения с shell
            # (маркер искажён/не найден), а не успех по умолчанию.
            raise AmneziaSSHError(
                message=f"Не удалось разобрать код возврата команды: {exit_info!r}",
                cmd=cmd,
                stdout=stdout_text.strip(),
                cause=e,
            ) from e
        stderr_text = ""
        try:
            while True:
                line = await asyncio.wait_for(
                    self._process.stderr.readline(), timeout=0.1
                )
                if not line:
                    break
                stderr_text += line
        except TimeoutError:
            pass

        return stdout_text.strip(), stderr_text.strip(), exit_code, cmd

    async def run_commands_in_container(
        self, commands: list[str]
    ) -> AsyncGenerator[tuple[str, str, int | None, str], None]:
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

    async def close(self) -> None:
        """Закрывает shell-сессию и соединение.

        Соединение к этому моменту может быть уже разорвано (например,
        `docker exec` в несуществующий контейнер завершил процесс раньше,
        чем мы попытались что-то в него записать) — попытка вежливо выйти
        командой `exit` в мёртвый канал сама кидает `BrokenPipeError`.
        Это ожидаемо при закрытии и не должно ни маскировать исходную
        ошибку, ни мешать закрыть соединение (`self._conn`) следом.
        """
        if self._process is not None:
            try:
                self._process.stdin.write("exit\n")
                await self._process.stdin.drain()
            except (BrokenPipeError, ConnectionError) as e:
                logger.bind(user=self.username).debug(
                    f"AsyncSSH: shell-сессия уже была разорвана при закрытии: {e}"
                )
            self._process = None

        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            logger.bind(user=self.username).debug("AsyncSSH: соединение закрыто")
            self._conn = None

    async def __aenter__(self) -> Self:
        """Открывает соединение в асинхронном контекстном менеджере.

        Returns
           Self: Текущий экземпляр клиента (в своём конкретном типе).

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
