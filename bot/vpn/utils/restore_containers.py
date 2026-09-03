import argparse
import asyncio

from loguru import logger

from bot.core.config import VPNNode, settings_bot
from bot.vpn.utils.amnezia_exceptions import AmneziaBackupError
from bot.vpn.utils.container_archive import (
    ArchiveCipher,
    BackupObject,
    ContainerArchiveTransport,
    ContainerBackupStorage,
)


class ContainerRestoreService:
    """Восстанавливает конфигурацию Amnezia-контейнера ноды из бэкапа в S3.

    Args:
        storage (ContainerBackupStorage): Хранилище архивов бэкапа в S3.
        cipher (ArchiveCipher): Расшифровка скачанного архива.

    """

    def __init__(self, storage: ContainerBackupStorage, cipher: ArchiveCipher) -> None:
        self._storage = storage
        self._cipher = cipher

    async def list_backups(self, name: str) -> list[BackupObject]:
        """Возвращает доступные бэкапы ноды, от старых к новым.

        Args:
            name (str): Имя ноды (ключ в `settings_bot.vpn.nodes`).

        Returns
            list[BackupObject]: Список доступных архивов.

        """
        return await self._storage.list_backups(name)

    async def restore_node(
        self, name: str, node: VPNNode, *, key: str | None = None
    ) -> str:
        """Восстанавливает `/opt/amnezia` контейнера ноды из бэкапа в S3.

        Полностью перезаписывает текущее содержимое `/opt/amnezia` в
        контейнере — предполагается, что вызывающий код уже получил
        подтверждение оператора.

        Args:
            name (str): Имя ноды (ключ в `settings_bot.vpn.nodes`).
            node (VPNNode): Конфигурация ноды.
            key (str | None): Ключ конкретного архива в S3. Если не задан —
                используется самый свежий бэкап ноды.

        Returns
            str: Ключ архива, из которого выполнено восстановление.

        Raises
            AmneziaBackupError: Если для ноды нет бэкапов либо расшифровка
                архива завершилась ошибкой.
            AmneziaSSHError: При ошибке доступа к контейнеру.

        """
        backup_key = key or await self._resolve_latest_key(name)
        logger.warning(
            f"Восстанавливаю ноду {name} ({node.host}) из {backup_key} — "
            f"текущие файлы в /opt/amnezia контейнера {node.container} будут перезаписаны"
        )
        encrypted = await self._storage.download(backup_key)
        archive = self._cipher.decrypt(encrypted)
        await ContainerArchiveTransport(node).write_archive(archive)
        logger.success(f"Нода {name} восстановлена из {backup_key}")
        return backup_key

    async def _resolve_latest_key(self, name: str) -> str:
        latest = await self._storage.latest_backup(name)
        if latest is None:
            raise AmneziaBackupError(f"Нет доступных бэкапов для ноды {name}")
        return latest.key


def _build_service() -> ContainerRestoreService:
    """Собирает `ContainerRestoreService` из глобальных настроек приложения."""
    storage = ContainerBackupStorage(settings_bot.bucket)
    cipher = ArchiveCipher(settings_bot.bucket.backup_encryption_key)
    return ContainerRestoreService(storage, cipher)


async def _print_backups(service: ContainerRestoreService, name: str) -> None:
    backups = await service.list_backups(name)
    if not backups:
        print(f"Бэкапов для ноды {name} не найдено")
        return
    for backup in backups:
        print(
            f"{backup.last_modified:%Y-%m-%d %H:%M:%S}  {backup.size:>10} bytes  {backup.key}"
        )


async def _restore(
    service: ContainerRestoreService, name: str, node: VPNNode, key: str | None
) -> None:
    used_key = await service.restore_node(name, node, key=key)
    restart_hint = f"docker restart {node.container}"
    if not node.use_local:
        restart_hint += f" (на {node.host})"
    print(f"Восстановлено из {used_key}. Перезапустите контейнер: {restart_hint}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Восстановление конфигурации Amnezia-контейнера из S3-бэкапа"
    )
    parser.add_argument(
        "--node",
        required=True,
        choices=sorted(settings_bot.vpn.nodes),
        help="Имя ноды",
    )
    parser.add_argument(
        "--list", action="store_true", help="Показать доступные бэкапы и выйти"
    )
    parser.add_argument(
        "--key", help="Ключ конкретного бэкапа в S3 (по умолчанию — самый свежий)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Не спрашивать подтверждение перед перезаписью",
    )
    return parser.parse_args()


def main() -> None:
    """Точка входа CLI восстановления конфигурации VPN-ноды из бэкапа."""
    args = _parse_args()
    node = settings_bot.vpn.nodes[args.node]
    service = _build_service()

    if args.list:
        asyncio.run(_print_backups(service, args.node))
        return

    if not args.yes:
        answer = input(
            f"Перезаписать /opt/amnezia контейнера {node.container} на {node.host} "
            f"данными из бэкапа? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Отменено")
            return

    asyncio.run(_restore(service, args.node, node, args.key))


if __name__ == "__main__":
    main()
