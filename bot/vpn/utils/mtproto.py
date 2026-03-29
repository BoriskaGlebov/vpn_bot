import asyncio
import shlex
from typing import Union

import asyncssh
from loguru import logger

from bot.vpn.utils.amnezia_exceptions import AmneziaSSHError
from bot.vpn.utils.amnezia_proxy import AsyncDockerSSHClient
from bot.vpn.utils.amnezia_wg import CONNECT_TIMEOUT


class HostDockerSSHClient(AsyncDockerSSHClient):
    """Асинхронный SSH-клиент для выполнения команд на Docker-хосте.

    Этот клиент наследуется от AsyncDockerSSHClient, но **не заходит внутрь контейнера** через `docker exec`.
    Используется для выполнения команд на хосте, например `docker logs <container>`.

    Attributes
        host (str): Хост или IP сервера для SSH.
        username (str | None): Имя пользователя для SSH.
        port (int): SSH порт.
        known_hosts (str | None): Путь к known_hosts.
        use_local (bool): Если True, команды исполняются локально через subprocess.

    """

    async def connect(self) -> None:
        """Устанавливает SSH-соединение с хостом.

        Не открывает shell в контейнере, только соединение с сервером.

        Raises
            AmneziaSSHError: Ошибка при подключении или таймаут SSH.

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
            logger.bind(user=self.username).debug(
                f"AsyncSSH: подключение к {self.host} установлено"
            )
        except TimeoutError:
            logger.bind(user=self.username).error(
                f"AsyncSSH: таймаут подключения к {self.host}"
            )
            raise AmneziaSSHError(
                f"SSH timeout при подключении к {self.host}:{self.port}"
            )
        except (OSError, asyncssh.Error) as exc:
            logger.bind(user=self.username).error(
                f"AsyncSSH: ошибка подключения: {exc}"
            )
            raise

    async def write_single_cmd(self, cmd: str) -> tuple[str, str, int, str]:
        """Выполняет команду на хосте напрямую, без захода внутрь контейнера.

        Args:
            cmd (str): Команда для выполнения.

        Returns
            Tuple[str, str, int, str]: Кортеж:
                - stdout (str): Стандартный вывод команды.
                - stderr (str): Стандартный поток ошибок.
                - exit_code (int): Код возврата команды.
                - cmd (str): Выполненная команда.

        Raises
            AmneziaSSHError: Если SSH-соединение не установлено.

        """
        if self.use_local:
            process = await asyncio.create_subprocess_shell(
                cmd,
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

        if self._conn is None:
            raise AmneziaSSHError("SSH-соединение не установлено. Вызови connect()")

        result = await self._conn.run(cmd)
        return result.stdout.strip(), result.stderr.strip(), result.exit_status, cmd


class MTProtoProxy:
    """Сервис для получения MTProto proxy-секрета через HostDockerSSHClient.

    Прокси-ссылка формируется для подключения Telegram MTProto:
        tg://proxy?server=<host>&port=<port>&secret=<secret>

    Рекомендуется использовать **поддомен с префиксом** для подключения,
    например: `f"{settings_bot.proxy_prefix}.{settings_bot.vpn_host}"`.
    Это помогает отделять разные прокси на одном хосте.

    Attributes
        client (HostDockerSSHClient): SSH-клиент для работы с сервером.
        container (str): Имя Docker-контейнера, из логов которого берётся secret.
        port (str): Порт MTProto прокси.

    """

    def __init__(
        self,
        client: Union[AsyncDockerSSHClient, "HostDockerSSHClient"],
        container: str = "telemt",
        port: str = "443",
    ) -> None:
        self.client = client
        self.container = container
        self.port = port

    def _build_tg_link(self, secret: str) -> str:
        """Формирует Telegram MTProto ссылку.

        Args:
            secret (str): Секретный ключ MTProto.

        Returns
            str: Ссылка вида tg://proxy?server=<host>&port=<port>&secret=<secret>

        """
        return f"tg://proxy?server={self.client.host}&port={self.port}&secret={secret}"

    async def get_secret(self) -> str:
        """Получает MTProto secret из логов контейнера на хосте.

        Returns
            str: Secret ключ MTProto.

        Raises
            AmneziaSSHError: Если не удалось получить или распарсить secret.

        """
        cmd = f"docker logs {shlex.quote(self.container)} | grep 'EE-TLS' | awk -F'secret=' '{{print $2}}'"
        stdout, stderr, code, _ = await self.client.write_single_cmd(cmd)
        if code != 0 or not stdout:
            raise AmneziaSSHError(
                "Не удалось получить MTProto secret",
                cmd=cmd,
                stdout=stdout,
                stderr=stderr,
            )
        return stdout.strip().splitlines()[-1].strip()

    async def get_proxy_link(self) -> str:
        """Формирует готовую ссылку для подключения MTProto proxy.

        Returns
            str: tg://proxy ссылка.

        Raises
            AmneziaSSHError: Если секрет не был получен.

        """
        secret = await self.get_secret()
        link = self._build_tg_link(secret)
        logger.success("MTProto ссылка успешно сформирована")
        return link
