from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.config import VPNNode
from bot.vpn.utils import restore_containers as rc
from bot.vpn.utils.amnezia_exceptions import AmneziaBackupError
from bot.vpn.utils.container_archive import BackupObject


@pytest.fixture
def node() -> VPNNode:
    return VPNNode(
        host="vpn.example.com", username="u", container="amnezia-awg2", use_local=False
    )


@pytest.fixture
def service() -> rc.ContainerRestoreService:
    storage = AsyncMock()
    cipher = MagicMock()
    return rc.ContainerRestoreService(storage, cipher)


@pytest.mark.vpn
async def test_restore_node_uses_explicit_key(service, node):
    service._storage.download.return_value = b"encrypted"
    service._cipher.decrypt.return_value = b"archive"
    transport = AsyncMock()

    with patch.object(
        rc, "ContainerArchiveTransport", return_value=transport
    ) as transport_cls:
        used_key = await service.restore_node(
            "sof", node, key="backup/containers/sof/x"
        )

    service._storage.download.assert_awaited_once_with("backup/containers/sof/x")
    service._storage.latest_backup.assert_not_called()
    service._cipher.decrypt.assert_called_once_with(b"encrypted")
    transport_cls.assert_called_once_with(node)
    transport.write_archive.assert_awaited_once_with(b"archive")
    assert used_key == "backup/containers/sof/x"


@pytest.mark.vpn
async def test_restore_node_resolves_latest_when_key_missing(service, node):
    service._storage.latest_backup.return_value = BackupObject(
        key="backup/containers/sof/latest", last_modified=datetime.now(UTC), size=1
    )
    service._storage.download.return_value = b"encrypted"
    service._cipher.decrypt.return_value = b"archive"
    transport = AsyncMock()

    with patch.object(rc, "ContainerArchiveTransport", return_value=transport):
        used_key = await service.restore_node("sof", node)

    service._storage.latest_backup.assert_awaited_once_with("sof")
    assert used_key == "backup/containers/sof/latest"


@pytest.mark.vpn
async def test_restore_node_no_backups_raises(service, node):
    service._storage.latest_backup.return_value = None

    with pytest.raises(AmneziaBackupError):
        await service.restore_node("sof", node)

    service._storage.download.assert_not_called()


@pytest.mark.vpn
async def test_list_backups_delegates_to_storage(service):
    expected = [BackupObject(key="k", last_modified=datetime.now(UTC), size=1)]
    service._storage.list_backups.return_value = expected

    result = await service.list_backups("sof")

    service._storage.list_backups.assert_awaited_once_with("sof")
    assert result == expected
