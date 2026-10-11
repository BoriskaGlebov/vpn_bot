import asyncio
import shlex

from loguru import logger

from bot.vpn.utils.amnezia_exceptions import AmneziaSSHError
from bot.vpn.utils.docker_ssh_client import AsyncDockerSSHClient


class HostDockerSSHClient(AsyncDockerSSHClient):
    """SSH-клиент для выполнения команд на Docker-хосте, а не внутри контейнера.

    Используется для команд уровня хоста — например `docker logs <container>`
    или `docker restart <container>` для контейнера, который сам не является
    целью выполнения (в отличие от `AsyncDockerSSHClient` при `in_container=True`,
    который заходит внутрь контейнера через `docker exec`). Вся разница с базовым
    `AsyncContainerShellClient` — в одном флаге `in_container=False`, остальной
    транспорт (подключение, одноразовый запуск команды) общий.

    Attributes
        host (str): Хост или IP сервера для SSH.
        username (str | None): Имя пользователя для SSH.
        port (int): SSH порт.
        known_hosts (str | None): Путь к known_hosts.
        use_local (bool): Если True, команды исполняются локально через subprocess.

    """

    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        known_hosts: str | None = None,
        use_local: bool = False,
    ) -> None:
        """Инициализация класса HostDockerSSHClient."""
        super().__init__(
            host=host,
            username=username,
            port=port,
            known_hosts=known_hosts,
            use_local=use_local,
            in_container=False,
        )


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
        client: AsyncDockerSSHClient,
        container: str = "telemt",
        port: int = 443,
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

    async def _fetch_secret(self) -> str | None:
        """Получает MTProto secret из логов контейнера.

        Returns
            Найденный secret или ``None``, если получить его не удалось.

        """
        cmd = (
            f"docker logs {shlex.quote(self.container)} 2>&1 "
            "| grep 'EE-TLS' "
            "| awk -F'secret=' '{print $2}'"
        )
        stdout, _, code, _ = await self.client.write_single_cmd(cmd)

        if code != 0 or not stdout:
            return None

        secret = stdout.strip().splitlines()[-1].strip()
        return secret or None

    async def get_secret(self) -> str:
        """Получает MTProto secret из логов контейнера.

        Если secret отсутствует в логах, контейнер перезапускается и
        выполняются повторные попытки чтения secret.

        Returns
            MTProto secret.

        Raises
            AmneziaSSHError: Если secret не удалось получить даже после
                перезапуска контейнера.

        """
        secret = await self._fetch_secret()
        if secret:
            return secret
        restart_cmd = f"docker restart {shlex.quote(self.container)}"
        await self.client.write_single_cmd(restart_cmd)

        await asyncio.sleep(5)

        for _ in range(10):
            secret = await self._fetch_secret()
            if secret:
                return secret
            await asyncio.sleep(2)

        raise AmneziaSSHError(
            "Не удалось получить MTProto secret после перезапуска контейнера",
            cmd=restart_cmd,
        )

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
