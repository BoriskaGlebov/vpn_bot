from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from bot.core.config import BucketSettings, VPNNode
from bot.vpn.utils import container_archive as ca
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


def _connect_cm(
    conn: AsyncMock | None = None, side_effect: Exception | None = None
) -> MagicMock:
    """Мок для `asyncssh.connect(...)`, используемого как `async with`."""
    cm = MagicMock()
    if side_effect is not None:
        cm.__aenter__ = AsyncMock(side_effect=side_effect)
    else:
        cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


# ===================== ContainerArchiveTransport =====================


@pytest.mark.vpn
async def test_read_archive_local_success(local_node):
    process = AsyncMock()
    process.communicate.return_value = (b"archive-bytes", b"")
    process.returncode = 0
    with patch.object(ca, "create_subprocess_exec", AsyncMock(return_value=process)):
        data = await ca.ContainerArchiveTransport(local_node).read_archive()
    assert data == b"archive-bytes"


@pytest.mark.vpn
async def test_read_archive_local_failure(local_node):
    process = AsyncMock()
    process.communicate.return_value = (b"", b"tar: not found")
    process.returncode = 1
    with patch.object(ca, "create_subprocess_exec", AsyncMock(return_value=process)):
        with pytest.raises(AmneziaSSHError):
            await ca.ContainerArchiveTransport(local_node).read_archive()


@pytest.mark.vpn
async def test_write_archive_local_passes_stdin(local_node):
    process = AsyncMock()
    process.communicate.return_value = (b"", b"")
    process.returncode = 0
    create = AsyncMock(return_value=process)
    with patch.object(ca, "create_subprocess_exec", create):
        await ca.ContainerArchiveTransport(local_node).write_archive(b"payload")
    process.communicate.assert_awaited_once_with(input=b"payload")
    assert create.call_args.kwargs["stdin"] == ca.subprocess.PIPE


@pytest.mark.vpn
async def test_read_archive_remote_success(remote_node):
    result = MagicMock(exit_status=0, stdout=b"archive-bytes", stderr=b"")
    conn = AsyncMock()
    conn.run.return_value = result
    with patch.object(ca.asyncssh, "connect", _connect_cm(conn=conn)):
        data = await ca.ContainerArchiveTransport(remote_node).read_archive()
    assert data == b"archive-bytes"


@pytest.mark.vpn
async def test_read_archive_remote_connect_error(remote_node):
    with patch.object(ca.asyncssh, "connect", _connect_cm(side_effect=OSError("boom"))):
        with pytest.raises(AmneziaSSHError):
            await ca.ContainerArchiveTransport(remote_node).read_archive()


@pytest.mark.vpn
async def test_read_archive_remote_command_error(remote_node):
    result = MagicMock(exit_status=1, stdout=b"", stderr=b"no such container")
    conn = AsyncMock()
    conn.run.return_value = result
    with patch.object(ca.asyncssh, "connect", _connect_cm(conn=conn)):
        with pytest.raises(AmneziaSSHError):
            await ca.ContainerArchiveTransport(remote_node).read_archive()


@pytest.mark.vpn
async def test_write_archive_remote_passes_input(remote_node):
    result = MagicMock(exit_status=0, stdout=b"", stderr=b"")
    conn = AsyncMock()
    conn.run.return_value = result
    with patch.object(ca.asyncssh, "connect", _connect_cm(conn=conn)):
        await ca.ContainerArchiveTransport(remote_node).write_archive(b"payload")
    assert conn.run.call_args.kwargs["input"] == b"payload"


# ===================== ArchiveCipher =====================


@pytest.mark.vpn
def test_cipher_missing_key_raises():
    cipher = ca.ArchiveCipher(None)
    with pytest.raises(AmneziaBackupError):
        cipher.encrypt(b"data")


@pytest.mark.vpn
def test_cipher_roundtrip():
    key = Fernet.generate_key()
    cipher = ca.ArchiveCipher(SecretStr(key.decode()))
    encrypted = cipher.encrypt(b"secret-data")
    assert encrypted != b"secret-data"
    assert cipher.decrypt(encrypted) == b"secret-data"


@pytest.mark.vpn
def test_cipher_decrypt_invalid_token():
    key = Fernet.generate_key()
    cipher = ca.ArchiveCipher(SecretStr(key.decode()))
    with pytest.raises(AmneziaBackupError):
        cipher.decrypt(b"not-a-valid-token")


# ===================== ContainerBackupStorage =====================


@pytest.fixture
def bucket() -> BucketSettings:
    return BucketSettings(
        bucket_name="bucket",
        prefix="media/",
        endpoint_url="https://s3.example.com",
        access_key=SecretStr("access"),
        secret_key=SecretStr("secret"),
    )


def _session_with_client(client: AsyncMock) -> MagicMock:
    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = client
    session = MagicMock()
    session.client.return_value = client_cm
    return session


@pytest.mark.vpn
async def test_storage_upload_success(bucket):
    s3 = AsyncMock()
    session = _session_with_client(s3)
    with patch.object(ca.aioboto3, "Session", return_value=session):
        key = await ca.ContainerBackupStorage(bucket).upload("main", b"encrypted")
    assert key.startswith("backup/containers/main/main_")
    s3.put_object.assert_awaited_once()
    assert s3.put_object.call_args.kwargs["Key"] == key
    assert s3.put_object.call_args.kwargs["Body"] == b"encrypted"


@pytest.mark.vpn
async def test_storage_upload_failure(bucket):
    session = MagicMock()
    session.client.side_effect = RuntimeError("s3 down")
    with patch.object(ca.aioboto3, "Session", return_value=session):
        with pytest.raises(AmneziaBackupError):
            await ca.ContainerBackupStorage(bucket).upload("main", b"encrypted")


@pytest.mark.vpn
async def test_storage_download_success(bucket):
    body = AsyncMock()
    body.read.return_value = b"archive-bytes"
    body.__aenter__.return_value = body
    s3 = AsyncMock()
    s3.get_object.return_value = {"Body": body}
    session = _session_with_client(s3)
    with patch.object(ca.aioboto3, "Session", return_value=session):
        data = await ca.ContainerBackupStorage(bucket).download(
            "backup/containers/main/x"
        )
    assert data == b"archive-bytes"


@pytest.mark.vpn
async def test_storage_list_backups_sorted(bucket):
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 2, 1, tzinfo=UTC)

    async def fake_paginate(**kwargs):
        yield {
            "Contents": [
                {
                    "Key": "backup/containers/main/main_new",
                    "LastModified": newer,
                    "Size": 20,
                },
                {
                    "Key": "backup/containers/main/main_old",
                    "LastModified": older,
                    "Size": 10,
                },
            ]
        }

    paginator = MagicMock()
    paginator.paginate = fake_paginate
    s3 = AsyncMock()
    s3.get_paginator = MagicMock(return_value=paginator)
    session = _session_with_client(s3)

    with patch.object(ca.aioboto3, "Session", return_value=session):
        backups = await ca.ContainerBackupStorage(bucket).list_backups("main")

    assert [b.key for b in backups] == [
        "backup/containers/main/main_old",
        "backup/containers/main/main_new",
    ]

    with patch.object(ca.aioboto3, "Session", return_value=session):
        latest = await ca.ContainerBackupStorage(bucket).latest_backup("main")
    assert latest is not None
    assert latest.key == "backup/containers/main/main_new"


@pytest.mark.vpn
async def test_storage_latest_backup_none(bucket):
    async def fake_paginate(**kwargs):
        return
        yield  # pragma: no cover

    paginator = MagicMock()
    paginator.paginate = fake_paginate
    s3 = AsyncMock()
    s3.get_paginator = MagicMock(return_value=paginator)
    session = _session_with_client(s3)

    with patch.object(ca.aioboto3, "Session", return_value=session):
        latest = await ca.ContainerBackupStorage(bucket).latest_backup("main")
    assert latest is None
