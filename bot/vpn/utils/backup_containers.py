import asyncio

from loguru import logger

from bot.core.config import VPNNode, settings_bot
from bot.vpn.utils.amnezia_exceptions import AmneziaBackupError
from bot.vpn.utils.container_archive import (
    ArchiveCipher,
    ContainerArchiveTransport,
    ContainerBackupStorage,
)


class ContainerBackupService:
    """Оркестрирует бэкап конфигураций Amnezia-контейнеров VPN-нод в S3.

    Args:
        storage (ContainerBackupStorage): Хранилище архивов бэкапа в S3.
        cipher (ArchiveCipher): Шифрование архивов перед загрузкой.

    """

    def __init__(self, storage: ContainerBackupStorage, cipher: ArchiveCipher) -> None:
        self._storage = storage
        self._cipher = cipher

    async def backup_node(self, name: str, node: VPNNode) -> str:
        """Бэкапит одну ноду: архивирует `/opt/amnezia`, шифрует и грузит в S3.

        Args:
            name (str): Имя ноды в реестре (`main`, `sof`, `waw`, ...).
            node (VPNNode): Конфигурация ноды.

        Returns
            str: Ключ загруженного объекта в S3.

        Raises
            AmneziaSSHError: При ошибке доступа к контейнеру.
            AmneziaBackupError: При ошибке шифрования или загрузки в S3.

        """
        logger.info(f"Бэкап контейнера ноды {name} ({node.host})...")
        archive = await ContainerArchiveTransport(node).read_archive()
        encrypted = self._cipher.encrypt(archive)
        key = await self._storage.upload(name, encrypted)
        logger.info(f"Бэкап ноды {name} загружен в S3: {key}")
        return key

    async def backup_all(self, nodes: dict[str, VPNNode]) -> list[str]:
        """Бэкапит контейнеры всех переданных VPN-нод.

        Ошибка на одной ноде не прерывает бэкап остальных — все ноды
        обрабатываются независимо, а по итогу собираются в одну ошибку.

        Args:
            nodes (dict[str, VPNNode]): Ноды в формате `{имя: конфигурация}`.

        Returns
            list[str]: Ключи успешно загруженных архивов в S3.

        Raises
            AmneziaBackupError: Если хотя бы одна нода не забэкапилась.

        """
        results = await asyncio.gather(
            *(self.backup_node(name, node) for name, node in nodes.items()),
            return_exceptions=True,
        )
        succeeded: list[str] = []
        failed: list[str] = []
        for name, result in zip(nodes, results):
            if isinstance(result, BaseException):
                logger.error(f"Бэкап ноды {name} завершился ошибкой: {result}")
                failed.append(name)
            else:
                succeeded.append(result)
        if failed:
            raise AmneziaBackupError(
                f"Бэкап контейнеров не удался для нод: {', '.join(failed)}"
            )
        return succeeded


def _build_service() -> ContainerBackupService:
    """Собирает `ContainerBackupService` из глобальных настроек приложения."""
    storage = ContainerBackupStorage(settings_bot.bucket)
    cipher = ArchiveCipher(settings_bot.bucket.backup_encryption_key)
    return ContainerBackupService(storage, cipher)


if __name__ == "__main__":
    uploaded_keys = asyncio.run(_build_service().backup_all(settings_bot.vpn.nodes))
    for uploaded_key in uploaded_keys:
        print(f"BACKUP_KEY::{uploaded_key}")
