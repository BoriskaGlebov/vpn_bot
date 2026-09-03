from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.config import VPNNode
from bot.vpn.utils import backup_containers as bc
from bot.vpn.utils.amnezia_exceptions import AmneziaBackupError, AmneziaSSHError


@pytest.fixture
def local_node() -> VPNNode:
    return VPNNode(
        host="127.0.0.1", username="u", container="amnezia-awg2", use_local=True
    )


@pytest.fixture
def remote_node() -> VPNNode:
    return VPNNode(
        host="vpn.example.com", username="u", container="amnezia-awg2", use_local=False
    )


@pytest.fixture
def service() -> bc.ContainerBackupService:
    storage = AsyncMock()
    cipher = MagicMock()
    return bc.ContainerBackupService(storage, cipher)


@pytest.mark.vpn
async def test_backup_node_reads_encrypts_and_uploads(service, local_node):
    transport = AsyncMock()
    transport.read_archive.return_value = b"archive"
    service._cipher.encrypt.return_value = b"encrypted"
    service._storage.upload.return_value = "backup/containers/main/main_x.tar.gz.enc"

    with patch.object(
        bc, "ContainerArchiveTransport", return_value=transport
    ) as transport_cls:
        key = await service.backup_node("main", local_node)

    transport_cls.assert_called_once_with(local_node)
    transport.read_archive.assert_awaited_once()
    service._cipher.encrypt.assert_called_once_with(b"archive")
    service._storage.upload.assert_awaited_once_with("main", b"encrypted")
    assert key == "backup/containers/main/main_x.tar.gz.enc"


@pytest.mark.vpn
async def test_backup_node_propagates_transport_error(service, remote_node):
    transport = AsyncMock()
    transport.read_archive.side_effect = AmneziaSSHError("ssh failed")

    with patch.object(bc, "ContainerArchiveTransport", return_value=transport):
        with pytest.raises(AmneziaSSHError):
            await service.backup_node("sof", remote_node)

    service._cipher.encrypt.assert_not_called()
    service._storage.upload.assert_not_called()


@pytest.mark.vpn
async def test_backup_all_success(service, local_node, remote_node):
    async def fake_backup_node(name: str, node: VPNNode) -> str:
        return f"backup/containers/{name}/{name}_x.tar.gz.enc"

    service.backup_node = fake_backup_node

    keys = await service.backup_all({"main": local_node, "sof": remote_node})

    assert sorted(keys) == [
        "backup/containers/main/main_x.tar.gz.enc",
        "backup/containers/sof/sof_x.tar.gz.enc",
    ]


@pytest.mark.vpn
async def test_backup_all_partial_failure(service, local_node, remote_node):
    async def fake_backup_node(name: str, node: VPNNode) -> str:
        if name == "sof":
            raise AmneziaSSHError("ssh failed")
        return "key"

    service.backup_node = fake_backup_node

    with pytest.raises(AmneziaBackupError, match="sof"):
        await service.backup_all({"main": local_node, "sof": remote_node})
