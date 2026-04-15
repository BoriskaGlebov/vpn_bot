import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from bot.vpn.utils.mtproto import (
    AmneziaSSHError,
    HostDockerSSHClient,
    MTProtoProxy,
)


@pytest.fixture
def client():
    c = HostDockerSSHClient(
        host="127.0.0.1",
        username="user",
        port=22,
        known_hosts=None,
    )
    c._conn = None
    return c


@pytest.fixture
def proxy(client):
    return MTProtoProxy(client=client, container="telemt", port="443")


@pytest.mark.asyncio
async def test_connect_success(client):
    with patch("asyncssh.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = AsyncMock()

        await client.connect()

        assert client._conn is not None
        mock_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_timeout(client):
    with patch("asyncssh.connect", side_effect=asyncio.TimeoutError):
        with pytest.raises(AmneziaSSHError):
            await client.connect()


@pytest.mark.asyncio
async def test_connect_asyncssh_error(client):
    with patch("asyncssh.connect", side_effect=asyncssh.Error(1, "fail")):
        with pytest.raises(asyncssh.Error):
            await client.connect()


@pytest.mark.asyncio
async def test_connect_already_connected(client):
    existing_conn = AsyncMock()
    client._conn = existing_conn

    await client.connect()

    assert client._conn is existing_conn


@pytest.mark.asyncio
async def test_connect_use_local():
    client = HostDockerSSHClient(
        host="127.0.0.1",
        username="user",
        port=22,
        known_hosts=None,
        use_local=True,
    )

    await client.connect()


@pytest.mark.asyncio
async def test_write_single_cmd_success(client):
    result = MagicMock()
    result.stdout = b"ok"
    result.stderr = b""
    result.exit_status = 0

    client._conn = AsyncMock()
    client._conn.run = AsyncMock(return_value=result)

    stdout, stderr, code, cmd = await client.write_single_cmd("ls")

    assert stdout == "ok"
    assert stderr == ""
    assert code == 0
    assert cmd == "ls"


@pytest.mark.asyncio
async def test_write_single_cmd_no_connection():
    client = HostDockerSSHClient(host="1", username="u", port=22)

    with pytest.raises(AmneziaSSHError):
        await client.write_single_cmd("ls")


@pytest.mark.asyncio
async def test_write_single_cmd_local():
    client = HostDockerSSHClient(
        host="1",
        username="u",
        port=22,
        use_local=True,
    )

    stdout, stderr, code, cmd = await client.write_single_cmd("echo hello")

    assert stdout == "hello"
    assert code == 0


@pytest.mark.asyncio
async def test_get_secret_success(proxy, client):
    client.write_single_cmd = AsyncMock(return_value=("abc123\nxyz789", "", 0, "cmd"))

    secret = await proxy.get_secret()

    assert secret == "xyz789"


@pytest.mark.asyncio
async def test_get_secret_empty(proxy, client):
    client.write_single_cmd = AsyncMock(return_value=("", "", 0, "cmd"))

    with pytest.raises(AmneziaSSHError):
        await proxy.get_secret()


@pytest.mark.asyncio
async def test_get_secret_fail_code(proxy, client):
    client.write_single_cmd = AsyncMock(return_value=("something", "error", 1, "cmd"))

    with pytest.raises(AmneziaSSHError):
        await proxy.get_secret()


def test_build_tg_link(proxy, client):
    link = proxy._build_tg_link("secret123")

    assert link == (f"tg://proxy?server={client.host}&port=443&secret=secret123")


@pytest.mark.asyncio
async def test_get_proxy_link_success(proxy):
    proxy.get_secret = AsyncMock(return_value="secret123")

    link = await proxy.get_proxy_link()

    assert "secret=secret123" in link
    assert link.startswith("tg://proxy")


@pytest.mark.asyncio
async def test_get_proxy_link_fail(proxy):
    proxy.get_secret = AsyncMock(side_effect=AmneziaSSHError("fail"))

    with pytest.raises(AmneziaSSHError):
        await proxy.get_proxy_link()
