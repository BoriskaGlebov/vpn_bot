import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.vpn.utils.amnezia_exceptions import AmneziaSSHError
from bot.vpn.utils.amnezia_proxy import AmneziaProxy, AsyncDockerSSHClient


@pytest.fixture
def proxy_client_local(monkeypatch):
    client = AsyncDockerSSHClient(
        host="127.0.0.1",
        username="localuser",
        container="proxy-container",
        use_local=True,
    )
    # ensure use_local used by instance, class sets from settings, overwrite
    client.use_local = True
    return client


@pytest.fixture
def proxy_client_ssh(monkeypatch):
    client = AsyncDockerSSHClient(
        host="10.0.0.1",
        username="vpnuser",
        container="proxy-container",
        use_local=False,
    )
    client.use_local = False
    return client


@pytest.fixture
def proxy(proxy_client_ssh):
    return AmneziaProxy(client=proxy_client_ssh, port="40711")


@pytest.mark.vpn
async def test_connect_local_mode_noop(proxy_client_local):
    # In local mode connect() should do nothing and not raise
    await proxy_client_local.connect()


@pytest.mark.vpn
async def test_connect_ssh_success(proxy_client_ssh):
    mock_conn = AsyncMock()
    mock_process = AsyncMock()
    with patch(
        "bot.vpn.utils.amnezia_proxy.asyncssh.connect", new_callable=AsyncMock
    ) as mock_connect:
        mock_connect.return_value = mock_conn
        mock_conn.create_process.return_value = mock_process
        await proxy_client_ssh.connect()
        mock_connect.assert_awaited()
        mock_conn.create_process.assert_awaited_once()
        assert proxy_client_ssh._conn is mock_conn
        assert proxy_client_ssh._process is mock_process


@pytest.mark.vpn
async def test_connect_ssh_timeout(proxy_client_ssh):
    with patch(
        "bot.vpn.utils.amnezia_proxy.asyncssh.connect", new_callable=AsyncMock
    ) as mock_connect:

        async def delayed(*args, **kwargs):
            await asyncio.sleep(0.2)
            return AsyncMock()

        mock_connect.side_effect = TimeoutError()
        with pytest.raises(AmneziaSSHError):
            await proxy_client_ssh.connect()


@pytest.mark.vpn
async def test_connect_ssh_os_error(proxy_client_ssh):
    with patch(
        "bot.vpn.utils.amnezia_proxy.asyncssh.connect", new_callable=AsyncMock
    ) as mock_connect:
        mock_connect.side_effect = OSError("connection error")
        with pytest.raises(OSError):
            await proxy_client_ssh.connect()


@pytest.mark.vpn
async def test_write_single_cmd_local(proxy_client_local, monkeypatch):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"out\n", b""))
    proc.returncode = 0
    monkeypatch.setattr(
        asyncio, "create_subprocess_shell", AsyncMock(return_value=proc)
    )

    stdout, stderr, code, cmd = await proxy_client_local.write_single_cmd("echo test")
    assert stdout == "out"
    assert stderr == ""
    assert code == 0
    assert cmd == "echo test"


@pytest.mark.vpn
async def test_write_single_cmd_ssh_flow(proxy_client_ssh):
    process_mock = AsyncMock()
    proxy_client_ssh._process = process_mock
    process_mock.stdin.write = MagicMock()
    process_mock.stdin.drain = AsyncMock()
    # produce some lines until marker
    process_mock.stdout.readuntil = AsyncMock(
        side_effect=["some out\n", "__EXIT__:0\n"]
    )
    process_mock.stderr.readline = AsyncMock(side_effect=TimeoutError)

    stdout, stderr, code, cmd = await proxy_client_ssh.write_single_cmd("whoami")
    assert stdout == "some out"
    assert stderr == ""
    assert code == 0
    assert cmd == "whoami"


@pytest.mark.vpn
async def test_write_single_cmd_no_process(proxy_client_ssh):
    proxy_client_ssh._process = None
    with pytest.raises(AmneziaSSHError):
        await proxy_client_ssh.write_single_cmd("date")


@pytest.mark.vpn
async def test_run_commands_in_container_iterates(proxy_client_local, monkeypatch):
    # mock write_single_cmd to yield two commands
    proxy_client_local.write_single_cmd = AsyncMock(
        side_effect=[("a", "", 0, "c1"), ("b", "", 0, "c2")]
    )
    cmds = ["c1", "c2"]
    results = []
    async for item in proxy_client_local.run_commands_in_container(cmds):
        results.append(item)
    assert results == [("a", "", 0, "c1"), ("b", "", 0, "c2")]


@pytest.mark.vpn
async def test_restart_container_local_success(proxy_client_local, monkeypatch):
    # patch docker SDK client
    fake_container = MagicMock()
    fake_container.restart = MagicMock()
    fake_docker_client = MagicMock()
    fake_docker_client.containers.get.return_value = fake_container

    with patch(
        "bot.vpn.utils.amnezia_proxy.docker.DockerClient",
        return_value=fake_docker_client,
    ):
        ok = await proxy_client_local.restart_container()
        assert ok is True
        fake_docker_client.containers.get.assert_called_once_with("proxy-container")
        fake_container.restart.assert_called_once()


@pytest.mark.vpn
async def test_restart_container_local_docker_exception(proxy_client_local):
    from docker.errors import DockerException

    fake_docker_client = MagicMock()
    fake_docker_client.containers.get.side_effect = DockerException("boom")
    with patch(
        "bot.vpn.utils.amnezia_proxy.docker.DockerClient",
        return_value=fake_docker_client,
    ):
        with pytest.raises(AmneziaSSHError) as exc:
            await proxy_client_local.restart_container()
        err = exc.value
        assert "Ошибка при перезапуске контейнера через Docker API" in str(err)
        assert err.cmd == "restart proxy-container"
        assert err.stderr


@pytest.mark.vpn
async def test_restart_container_ssh_success(proxy_client_ssh):
    mock_result = AsyncMock()
    mock_result.exit_status = 0
    mock_result.stdout = "OK"
    mock_result.stderr = ""
    proxy_client_ssh._conn = AsyncMock()
    proxy_client_ssh._conn.run = AsyncMock(return_value=mock_result)

    ok = await proxy_client_ssh.restart_container()
    assert ok is True


@pytest.mark.vpn
async def test_restart_container_ssh_error(proxy_client_ssh):
    mock_result = AsyncMock()
    mock_result.exit_status = 1
    mock_result.stdout = ""
    mock_result.stderr = "bad"
    proxy_client_ssh._conn = AsyncMock()
    proxy_client_ssh._conn.run = AsyncMock(return_value=mock_result)

    with pytest.raises(AmneziaSSHError) as exc:
        await proxy_client_ssh.restart_container()
    err = exc.value
    assert "Ошибка при перезапуске контейнера" in str(err)
    assert err.stderr == "bad"


@pytest.mark.vpn
async def test_close_handles_process_and_conn(proxy_client_ssh):
    proc = AsyncMock()
    proc.close = MagicMock()
    proc.wait_closed = AsyncMock()

    conn = AsyncMock()
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()

    proxy_client_ssh._process = proc
    proxy_client_ssh._conn = conn

    await proxy_client_ssh.close()

    proc.close.assert_called_once()
    proc.wait_closed.assert_awaited_once()
    conn.close.assert_called_once()
    conn.wait_closed.assert_awaited_once()
    assert proxy_client_ssh._conn is None


@pytest.mark.vpn
async def test_aenter_aexit(proxy_client_ssh, monkeypatch):
    proxy_client_ssh.connect = AsyncMock()
    proxy_client_ssh.close = AsyncMock()
    async with proxy_client_ssh as c:
        assert c is proxy_client_ssh
    proxy_client_ssh.connect.assert_awaited_once()
    proxy_client_ssh.close.assert_awaited_once()


# AmneziaProxy tests


@pytest.mark.vpn
async def test_check_container_ok(proxy):
    proxy.client.write_single_cmd = AsyncMock(return_value=("root", "", 0, "whoami"))
    ok = await proxy._check_container()
    assert ok is True


@pytest.mark.vpn
async def test_check_container_not_root(proxy):
    proxy.client.write_single_cmd = AsyncMock(return_value=("ubuntu", "", 0, "whoami"))
    with pytest.raises(AmneziaSSHError) as exc:
        await proxy._check_container()
    err = exc.value
    assert "Контейнер" in str(err)
    assert err.stdout == "ubuntu"


@pytest.mark.vpn
async def test_build_tg_link(proxy):
    link = proxy._build_tg_link("user", "pass")
    assert "https://t.me/socks?" in link
    assert "server=10.0.0.1" in link
    assert "port=40711" in link
    assert "user=user" in link and "pass=pass" in link


@pytest.mark.vpn
async def test_add_user_new_creates_and_restarts(proxy):
    proxy.client.write_single_cmd = AsyncMock(
        side_effect=[
            ("", "", 1, "grep"),  # user not exists
            ("", "", 0, "append"),  # echo append ok
        ]
    )
    proxy.client.restart_container = AsyncMock(return_value=True)

    link = await proxy.add_user("alice", "pwd")
    assert "server=10.0.0.1" in link
    proxy.client.restart_container.assert_awaited_once()


@pytest.mark.vpn
async def test_add_user_existing_returns_link(proxy):
    proxy.client.write_single_cmd = AsyncMock(
        return_value=("alice:CL:oldpwd", "", 0, "grep")
    )
    link = await proxy.add_user("alice", "new")
    assert "oldpwd" in link


@pytest.mark.vpn
async def test_add_user_bad_format(proxy):
    proxy.client.write_single_cmd = AsyncMock(return_value=("alice:CL", "", 0, "grep"))
    with pytest.raises(AmneziaSSHError):
        await proxy.add_user("alice", "pwd")


@pytest.mark.vpn
async def test_add_user_invalid_colon(proxy):
    with pytest.raises(ValueError):
        await proxy.add_user("al:ice", "pwd")
    with pytest.raises(ValueError):
        await proxy.add_user("alice", "pw:d")


@pytest.mark.vpn
async def test_add_user_append_error(proxy):
    proxy.client.write_single_cmd = AsyncMock(
        side_effect=[
            ("", "", 1, "grep"),
            ("", "err", 1, "append"),
        ]
    )
    with pytest.raises(AmneziaSSHError):
        await proxy.add_user("bob", "pwd")


@pytest.mark.vpn
async def test_delete_user_success(proxy):
    proxy.client.write_single_cmd = AsyncMock(
        side_effect=[
            ("", "", 0, "check"),
            ("", "", 0, "sed"),
        ]
    )
    proxy.client.restart_container = AsyncMock(return_value=True)

    ok = await proxy.delete_user("alice")
    assert ok is True
    proxy.client.restart_container.assert_awaited_once()


@pytest.mark.vpn
async def test_delete_user_not_found(proxy):
    proxy.client.write_single_cmd = AsyncMock(return_value=("", "", 1, "check"))
    ok = await proxy.delete_user("alice")
    assert ok is False


@pytest.mark.vpn
async def test_delete_user_error(proxy):
    proxy.client.write_single_cmd = AsyncMock(
        side_effect=[
            ("", "", 0, "check"),
            ("", "boom", 1, "sed"),
        ]
    )
    with pytest.raises(AmneziaSSHError):
        await proxy.delete_user("alice")


@pytest.mark.vpn
async def test_delete_user_invalid_colon(proxy):
    with pytest.raises(ValueError):
        await proxy.delete_user("al:ice")


@pytest.mark.vpn
async def test_reload_3proxy_success(proxy):
    proxy.client.write_single_cmd = AsyncMock(return_value=("", "", 0, "pkill"))
    ok = await proxy.reload_3proxy()
    assert ok is True


@pytest.mark.vpn
async def test_reload_3proxy_error(proxy):
    proxy.client.write_single_cmd = AsyncMock(return_value=("", "err", 1, "pkill"))
    with pytest.raises(AmneziaSSHError):
        await proxy.reload_3proxy()
