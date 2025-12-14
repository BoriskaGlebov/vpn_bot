import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.vpn.utils.amnezia_exceptions import (
    AmneziaConfigError,
    AmneziaError,
    AmneziaSSHError,
)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_connect_success(ssh_client, mock_asyncssh_connect):
    mock_connect, mock_conn, mock_process = mock_asyncssh_connect

    await ssh_client.connect()

    mock_connect.assert_awaited_once_with(
        host="127.0.0.1",
        port=22,
        username="testuser",
        agent_forwarding=True,
        known_hosts=None,
    )
    mock_conn.create_process.assert_awaited_once()
    assert ssh_client._conn is mock_conn
    assert ssh_client._process is mock_process


@pytest.mark.vpn
@pytest.mark.vpn
async def test_connect_failure(ssh_client, mock_asyncssh_connect):
    mock_connect, _, _ = mock_asyncssh_connect
    mock_connect.side_effect = OSError("connection error")

    with pytest.raises(OSError):
        await ssh_client.connect()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_write_single_cmd_success(ssh_client):
    process_mock = AsyncMock()
    ssh_client._process = process_mock
    process_mock.stdin.write = AsyncMock()
    process_mock.stdin.drain = AsyncMock()
    process_mock.stdout.readuntil = AsyncMock(side_effect=["output\n", "__EXIT__:0\n"])
    process_mock.stderr.readline = AsyncMock(side_effect=TimeoutError)

    result = await ssh_client.write_single_cmd("echo test")
    assert result == ("output", "", 0, "echo test")


@pytest.mark.vpn
@pytest.mark.vpn
async def test_write_single_cmd_no_process(ssh_client):
    ssh_client._process = None
    with pytest.raises(AmneziaSSHError):
        await ssh_client.write_single_cmd("echo test")


@pytest.mark.vpn
@pytest.mark.vpn
async def test_write_single_cmd_success(ssh_client):
    mock_stdin = MagicMock()
    mock_stdin.drain = AsyncMock()

    mock_stdout = AsyncMock()
    mock_stdout.readuntil = AsyncMock(return_value="__EXIT__:0\n")

    mock_stderr = AsyncMock()
    mock_stderr.readline = AsyncMock(return_value="")

    ssh_client._process = MagicMock()
    ssh_client._process.stdin = mock_stdin
    ssh_client._process.stdout = mock_stdout
    ssh_client._process.stderr = mock_stderr

    result = await ssh_client.write_single_cmd("echo test")
    assert result[0] == ""
    assert result[1] == ""
    assert result[2] == 0


@pytest.mark.vpn
@pytest.mark.vpn
async def test_check_container_failure_not_root(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(return_value=("ubuntu", "", 0, "whoami"))

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._check_container()

    error = excinfo.value
    assert "Контейнер" in str(error)
    assert error.stdout == "ubuntu"
    assert error.cmd == "whoami"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_check_container_failure_error_in_cmd(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("", "command not found", 1, "whoami")
    )

    with pytest.raises(AmneziaSSHError):
        await ssh_client._check_container()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_generate_private_key_ok(ssh_client):
    async def fake_gen(commands):
        for cmd in commands:
            yield "PRIVATE_KEY", "", 0, cmd

    ssh_client.run_commands_in_container = fake_gen
    key = await ssh_client._generate_private_key()
    assert key == "PRIVATE_KEY"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_generate_private_key_error(ssh_client):
    async def fake_gen(commands):
        for cmd in commands:
            yield "", "critical error", 1, cmd

    ssh_client.run_commands_in_container = fake_gen
    with pytest.raises(AmneziaSSHError):
        await ssh_client._generate_private_key()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_generate_public_key_success(ssh_client):
    async def mock_gen(_):
        yield "PUBLIC_KEY_DATA", "", 0, "cat publickey"

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._generate_public_key()

    assert result == "PUBLIC_KEY_DATA"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_generate_public_key_error_stderr(ssh_client):
    async def mock_gen(_):
        yield "", "Ошибка генерации ключа", 1, "cat publickey"

    ssh_client.run_commands_in_container = mock_gen

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._generate_public_key()

    err = excinfo.value
    assert "Ошибка при генерации публичного ключа" in str(err)
    assert "Ошибка генерации ключа" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_generate_public_key_none(ssh_client):
    async def mock_gen(_):
        if False:
            yield

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._generate_public_key()

    assert result is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_vpn_params_config_ok(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            "[Interface]\nListenPort = 51820\nH1 = test\n[Peer]\n",
            "",
            0,
            "cmd",
        )
    )
    params, port = await ssh_client._get_vpn_params_config()
    assert port == 51820
    assert params["H1"] == "test"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_vpn_params_config_error(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("", "file not found", 1, "cmd")
    )
    with pytest.raises(AmneziaConfigError) as error:
        await ssh_client._get_vpn_params_config()
    assert "Ошибка получении конфига параметров VPN" in str(error)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_correct_ip_success(ssh_client):
    async def mock_gen(_):
        yield "10.0.0.1/32", "", 0, "cat lastip"

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._get_correct_ip()

    assert result == "10.0.0.2/32"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_correct_ip_invalid_ip(ssh_client):
    async def mock_gen(_):
        yield "invalid_ip/32", "", 0, "cat lastip"

    ssh_client.run_commands_in_container = mock_gen

    with pytest.raises(ValueError):
        await ssh_client._get_correct_ip()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_correct_ip_stderr(ssh_client):
    async def mock_gen(_):
        yield "", "Ошибка чтения файла", 1, "cat lastip"

    ssh_client.run_commands_in_container = mock_gen

    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._get_correct_ip()

    err = excinfo.value
    assert "Ошибка при получении IP" in str(err)
    assert err.file == "/opt/amnezia/awg/wg0.conf"
    assert "Ошибка чтения файла" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_correct_ip_none(ssh_client):
    async def mock_gen(_):
        if False:
            yield

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._get_correct_ip()

    assert result is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_psk_key_success(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(return_value=("PSK_KEY_DATA", "", 0, "cat"))

    result = await ssh_client._get_psk_key()

    ssh_client.write_single_cmd.assert_awaited_once_with(
        "cat /opt/amnezia/awg/wireguard_psk.key"
    )
    assert result == "PSK_KEY_DATA"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_psk_key_stderr(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("", "Ошибка чтения файла", 1, "cat")
    )

    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._get_psk_key()

    err = excinfo.value
    assert "Ошибка при получении PSK" in str(err)
    assert err.file == "/opt/amnezia/awg/wireguard_psk.key"
    assert "Ошибка чтения файла" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_psk_key_none(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(return_value=("", "", 0, "cat"))

    result = await ssh_client._get_psk_key()
    assert result is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_public_server_key_success(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("SERVER_PUBLIC_KEY", "", 0, "cat")
    )

    result = await ssh_client._get_public_server_key()

    ssh_client.write_single_cmd.assert_awaited_once_with(
        "cat wireguard_server_public_key.key"
    )
    assert result == "SERVER_PUBLIC_KEY"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_public_server_key_stderr(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("", "Ошибка чтения файла", 1, "cat")
    )

    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._get_public_server_key()

    err = excinfo.value
    assert "Ошибка при получении public key сервера" in str(err)
    assert err.file == "wireguard_server_public_key.key"
    assert "Ошибка чтения файла" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_get_public_server_key_none(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(return_value=("", "", 0, "cat"))

    result = await ssh_client._get_public_server_key()
    assert result is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_user_in_config_success(ssh_client):
    async def mock_gen(cmd):
        yield "OK", "", 0, cmd[-1]

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._add_user_in_config(
        public_server_key="PUB_KEY",
        correct_ip="10.0.0.2/32",
        psk_key="PSK_KEY",
    )

    assert result == "OK"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_user_in_config_stderr(ssh_client):
    async def mock_gen(cmds):
        yield "", "Ошибка при добавлении", 1, cmds[-1]

    ssh_client.run_commands_in_container = mock_gen

    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._add_user_in_config(
            public_server_key="PUB_KEY",
            correct_ip="10.0.0.2/32",
            psk_key="PSK_KEY",
        )

    err = excinfo.value
    assert "Ошибка при добавлении нового пользователя" in str(err)
    assert err.file == ssh_client.WG_CONF
    assert "Ошибка при добавлении" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_user_in_config_none(ssh_client):
    async def mock_gen(cmds):
        yield "", "", 0, cmds[-1]

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._add_user_in_config(
        public_server_key="PUB_KEY",
        correct_ip="10.0.0.2/32",
        psk_key="PSK_KEY",
    )

    assert result is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_generate_wg_config_success(ssh_client):
    ssh_client._get_vpn_params_config = AsyncMock(
        return_value=({"Jc": "value1", "H1": "value2"}, 51820)
    )

    new_ip = "10.0.0.2/32"
    private_key = "PRIVATE_KEY"
    pub_server_key = "PUB_SERVER_KEY"
    preshared_key = "PSK_KEY"

    result = await ssh_client._generate_wg_config(
        new_ip, private_key, pub_server_key, preshared_key
    )

    assert "[Interface]" in result
    assert "[Peer]" in result
    assert f"Address = {new_ip}" in result
    assert f"PrivateKey = {private_key}" in result
    assert f"PublicKey = {pub_server_key}" in result
    assert f"PresharedKey = {preshared_key}" in result
    assert f"Endpoint = {ssh_client.host}:51820" in result
    assert "Jc = value1" in result
    assert "H1 = value2" in result


@pytest.mark.vpn
@pytest.mark.vpn
async def test_reboot_interface_success(ssh_client):
    async def mock_gen(cmds):
        yield "Interface restarted", "", 0, cmds[-1]

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._reboot_interface()
    assert result is True


@pytest.mark.vpn
@pytest.mark.vpn
async def test_reboot_interface_warning(ssh_client):
    async def mock_gen(cmds):
        yield "", "Warning: minor issue", 0, cmds[-1]

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._reboot_interface()
    assert result == True


@pytest.mark.vpn
@pytest.mark.vpn
async def test_reboot_interface_error(ssh_client):
    async def mock_gen(cmds):
        yield "", "Fatal error", 1, cmds[-1]

    ssh_client.run_commands_in_container = mock_gen

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._reboot_interface()

    err = excinfo.value
    assert "Ошибка при перезапуске интерфейса" in str(err)
    assert err.stderr == "Fatal error"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_save_wg_config_success(ssh_client):
    ssh_client._generate_wg_config = AsyncMock(
        return_value="[Interface]\nAddress=10.0.0.2/32"
    )

    with patch(
        "bot.vpn.utils.amnezia_wg.aiofiles.open", create=True
    ) as mock_aiofiles_open:
        mock_file = AsyncMock()
        mock_aiofiles_open.return_value.__aenter__.return_value = mock_file

        result = await ssh_client._save_wg_config(
            filename="test.conf",
            new_ip="10.0.0.2/32",
            private_key="PRIVATE_KEY",
            pub_server_key="PUB_KEY",
            preshared_key="PSK_KEY",
        )

        assert isinstance(result, Path)
        ssh_client._generate_wg_config.assert_awaited_once_with(
            "10.0.0.2/32", "PRIVATE_KEY", "PUB_KEY", "PSK_KEY"
        )

        mock_aiofiles_open.assert_called_once()
        mock_file.write.assert_awaited_once_with("[Interface]\nAddress=10.0.0.2/32")
        result.unlink(missing_ok=True)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_save_wg_config_auto_conf_extension(ssh_client):
    ssh_client._generate_wg_config = AsyncMock(
        return_value="[Interface]\nAddress=10.0.0.3/32"
    )

    with patch(
        "bot.vpn.utils.amnezia_wg.aiofiles.open", create=True
    ) as mock_aiofiles_open:
        mock_file = AsyncMock()
        mock_aiofiles_open.return_value.__aenter__.return_value = mock_file

        filename = "user_config"
        result = await ssh_client._save_wg_config(
            filename=filename,
            new_ip="10.0.0.3/32",
            private_key="PRIVATE_KEY",
            pub_server_key="PUB_KEY",
            preshared_key="PSK_KEY",
        )

        assert isinstance(result, Path)
        assert result.suffix == ".conf"

        mock_aiofiles_open.assert_called_once_with(result, "w", encoding="utf-8")
        mock_file.write.assert_awaited_once_with("[Interface]\nAddress=10.0.0.3/32")
        result.unlink(missing_ok=True)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_to_clients_table_success(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(json.dumps([]), "", 0, f"cat {ssh_client.WG_CLIENTS_TABLE}")
    )
    mock_result = AsyncMock()
    mock_result.exit_status = 0
    mock_result.stdout = "OK"
    mock_result.stderr = ""
    ssh_client._conn = AsyncMock()
    ssh_client._conn.run = AsyncMock(return_value=mock_result)

    result = await ssh_client._add_to_clients_table("PUB_KEY", "Test Client")
    assert result is True
    ssh_client.write_single_cmd.assert_awaited_once()
    ssh_client._conn.run.assert_awaited_once()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_to_clients_table_client_exists(ssh_client):
    existing_data = [{"clientId": "PUB_KEY", "userData": {"clientName": "Test Client"}}]
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            json.dumps(existing_data),
            "",
            0,
            f"cat {ssh_client.WG_CLIENTS_TABLE}",
        )
    )

    result = await ssh_client._add_to_clients_table("PUB_KEY", "Test Client")
    assert result is True


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_to_clients_table_stderr(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            "",
            "Ошибка чтения файла",
            1,
            f"cat {ssh_client.WG_CLIENTS_TABLE}",
        )
    )

    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._add_to_clients_table("PUB_KEY", "Test Client")
    err = excinfo.value
    assert "Ошибка при чтении clientsTable" in str(err)
    assert err.file == ssh_client.WG_CLIENTS_TABLE
    assert "Ошибка чтения файла" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_to_clients_table_bad_json(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("невалидный JSON", "", 0, f"cat {ssh_client.WG_CLIENTS_TABLE}")
    )

    with pytest.raises(json.JSONDecodeError):
        await ssh_client._add_to_clients_table("PUB_KEY", "Test Client")


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_to_clients_table_docker_write_error(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(json.dumps([]), "", 0, f"cat {ssh_client.WG_CLIENTS_TABLE}")
    )

    mock_result = AsyncMock()
    mock_result.exit_status = 1
    mock_result.stdout = ""
    mock_result.stderr = "Ошибка записи"
    ssh_client._conn = AsyncMock()
    ssh_client._conn.run = AsyncMock(return_value=mock_result)

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._add_to_clients_table("PUB_KEY", "Test Client")
    err = excinfo.value
    assert "Ошибка при записи clientsTable" in str(err)
    assert err.stderr == "Ошибка записи"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_temp_files_success(ssh_client):
    async def mock_gen(cmd):
        for c in cmd:
            yield f"{c} удален", "", 0, c[-1]

    ssh_client.run_commands_in_container = mock_gen

    result = await ssh_client._delete_temp_files()
    assert result is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_temp_files_stderr(ssh_client):
    async def mock_gen(cmd):
        yield "", "", 0, cmd[0]
        yield "", "Ошибка удаления", 1, cmd[1]

    ssh_client.run_commands_in_container = mock_gen

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._delete_temp_files()

    err = excinfo.value
    assert "Ошибка при удалении временных файлов" in str(err)
    assert "Ошибка удаления" in err.stderr


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_new_user_gen_config_success(ssh_client):
    ssh_client._check_container = AsyncMock()
    ssh_client._generate_private_key = AsyncMock(return_value="PRIVATE_KEY")
    ssh_client._generate_public_key = AsyncMock(return_value="PUB_KEY")
    ssh_client._get_public_server_key = AsyncMock(return_value="PUB_SERVER_KEY")
    ssh_client._get_correct_ip = AsyncMock(return_value="10.0.0.2/32")
    ssh_client._get_psk_key = AsyncMock(return_value="PSK_KEY")
    ssh_client._add_user_in_config = AsyncMock(return_value="OK")
    ssh_client._add_to_clients_table = AsyncMock(return_value=True)
    ssh_client._save_wg_config = AsyncMock(return_value=True)
    ssh_client._delete_temp_files = AsyncMock()
    ssh_client._reboot_interface = AsyncMock()

    await ssh_client.add_new_user_gen_config("user.conf")

    ssh_client._check_container.assert_awaited_once()
    ssh_client._generate_private_key.assert_awaited_once()
    assert ssh_client._generate_private_key.return_value == "PRIVATE_KEY"
    ssh_client._generate_public_key.assert_awaited_once()
    assert ssh_client._generate_public_key.return_value == "PUB_KEY"
    ssh_client._get_public_server_key.assert_awaited_once()
    assert ssh_client._get_public_server_key.return_value == "PUB_SERVER_KEY"
    ssh_client._get_correct_ip.assert_awaited_once()
    assert ssh_client._get_correct_ip.return_value == "10.0.0.2/32"
    ssh_client._get_psk_key.assert_awaited_once()
    assert ssh_client._get_psk_key.return_value == "PSK_KEY"
    ssh_client._add_user_in_config.assert_awaited_once()
    assert ssh_client._add_user_in_config.return_value == "OK"
    ssh_client._add_to_clients_table.assert_awaited_once()
    assert ssh_client._add_to_clients_table.return_value == True
    ssh_client._save_wg_config.assert_awaited_once()
    assert ssh_client._save_wg_config.return_value == True
    ssh_client._delete_temp_files.assert_awaited_once()
    ssh_client._reboot_interface.assert_awaited_once()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_add_new_user_gen_config_raises_amnezia_error(ssh_client):
    ssh_client._check_container = AsyncMock(side_effect=AmneziaError("Container error"))

    with pytest.raises(AmneziaError) as excinfo:
        await ssh_client.add_new_user_gen_config("user.conf")

    err = excinfo.value
    assert "Container error" in str(err)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_user_wg0_success(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            "[Peer]\nPublicKey = PUB_KEY_TO_DELETE\nAllowedIPs = 10.0.0.2/32\n",
            "",
            0,
            f"cat {ssh_client.WG_CONF}",
        )
    )

    ssh_client._conn = AsyncMock()
    ssh_client._conn.run = AsyncMock(
        return_value=MagicMock(exit_status=0, stdout="", stderr="")
    )

    result = await ssh_client._delete_user_wg0("PUB_KEY_TO_DELETE")
    assert result is True
    ssh_client.write_single_cmd.assert_awaited_once()
    ssh_client._conn.run.assert_awaited_once()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_user_wg0_not_found(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            "[Peer]\nPublicKey = SOME_OTHER_KEY\nAllowedIPs = 10.0.0.2/32\n",
            "",
            0,
            f"cat {ssh_client.WG_CONF}",
        )
    )
    result = await ssh_client._delete_user_wg0("PUB_KEY_TO_DELETE")
    assert result is False


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_user_wg0_read_error(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=("", "Ошибка чтения файла", 1, f"cat {ssh_client.WG_CONF}")
    )
    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._delete_user_wg0("PUB_KEY_TO_DELETE")
    err = excinfo.value
    assert "Ошибка при чтении конфига" in str(err)
    assert err.file == ssh_client.WG_CONF


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_user_wg0_write_error(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            "[Peer]\nPublicKey = PUB_KEY_TO_DELETE\nAllowedIPs = 10.0.0.2/32\n",
            "",
            0,
            f"cat {ssh_client.WG_CONF}",
        )
    )
    ssh_client._conn = AsyncMock()
    ssh_client._conn.run = AsyncMock(
        return_value=MagicMock(exit_status=1, stdout="", stderr="Ошибка записи")
    )

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._delete_user_wg0("PUB_KEY_TO_DELETE")
    err = excinfo.value
    assert "Ошибка записи wg0.conf" in str(err)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_from_clients_table_success(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            json.dumps([{"clientId": "PUB_KEY"}]),
            "",
            0,
            f"cat {ssh_client.WG_DIR}/clientsTable",
        )
    )
    ssh_client._conn = AsyncMock()
    ssh_client._conn.run = AsyncMock(
        return_value=MagicMock(exit_status=0, stdout="", stderr="")
    )

    result = await ssh_client._delete_from_clients_table("PUB_KEY")
    assert result is True
    ssh_client.write_single_cmd.assert_awaited_once()
    ssh_client._conn.run.assert_awaited_once()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_from_clients_table_not_found(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            json.dumps([{"clientId": "OTHER_KEY"}]),
            "",
            0,
            f"cat {ssh_client.WG_DIR}/clientsTable",
        )
    )
    result = await ssh_client._delete_from_clients_table("PUB_KEY")
    assert result is False


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_from_clients_table_read_error(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            "",
            "Ошибка чтения файла",
            1,
            f"cat {ssh_client.WG_DIR}/clientsTable",
        )
    )
    with pytest.raises(AmneziaConfigError) as excinfo:
        await ssh_client._delete_from_clients_table("PUB_KEY")
    err = excinfo.value
    assert "Не удалось прочитать" in str(err)
    assert err.file == f"{ssh_client.WG_DIR}/clientsTable"


@pytest.mark.vpn
@pytest.mark.vpn
async def test_delete_from_clients_table_write_error(ssh_client):
    ssh_client.write_single_cmd = AsyncMock(
        return_value=(
            json.dumps([{"clientId": "PUB_KEY"}]),
            "",
            0,
            f"cat {ssh_client.WG_DIR}/clientsTable",
        )
    )
    ssh_client._conn = AsyncMock()
    ssh_client._conn.run = AsyncMock(
        return_value=MagicMock(exit_status=1, stdout="", stderr="Ошибка записи")
    )

    with pytest.raises(AmneziaSSHError) as excinfo:
        await ssh_client._delete_from_clients_table("PUB_KEY")
    err = excinfo.value
    assert "Ошибка при удалении ключа" in str(err)


@pytest.mark.vpn
@pytest.mark.vpn
async def test_full_delete_user_success(ssh_client):
    ssh_client._delete_user_wg0 = AsyncMock(return_value=True)
    ssh_client._delete_from_clients_table = AsyncMock(return_value=True)
    ssh_client._reboot_interface = AsyncMock(return_value=True)

    result = await ssh_client.full_delete_user("PUB_KEY")
    assert result is True
    ssh_client._delete_user_wg0.assert_awaited_once_with("PUB_KEY")
    ssh_client._delete_from_clients_table.assert_awaited_once_with("PUB_KEY")
    ssh_client._reboot_interface.assert_awaited_once()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_full_delete_user_not_found(ssh_client):
    ssh_client._delete_user_wg0 = AsyncMock(return_value=True)
    ssh_client._delete_from_clients_table = AsyncMock(return_value=False)
    ssh_client._reboot_interface = AsyncMock()

    result = await ssh_client.full_delete_user("PUB_KEY")
    assert result is False
    ssh_client._reboot_interface.assert_not_awaited()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_full_delete_user_exception(ssh_client):
    ssh_client._delete_user_wg0 = AsyncMock(side_effect=AmneziaError("Ошибка"))
    ssh_client._delete_from_clients_table = AsyncMock()
    ssh_client._reboot_interface = AsyncMock()

    with pytest.raises(AmneziaError):
        await ssh_client.full_delete_user("PUB_KEY")
    ssh_client._delete_from_clients_table.assert_not_awaited()
    ssh_client._reboot_interface.assert_not_awaited()


@pytest.mark.vpn
@pytest.mark.vpn
async def test_close(ssh_client):
    mock_stdin = MagicMock()
    mock_stdin.drain = AsyncMock()

    ssh_client._process = MagicMock()
    ssh_client._process.stdin = mock_stdin

    mock_conn = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    ssh_client._conn = mock_conn

    await ssh_client.close()

    # Проверяем, что shell корректно завершён
    mock_stdin.write.assert_called_once_with("exit\n")
    mock_stdin.drain.assert_awaited_once()

    # Проверяем, что соединение закрыто
    mock_conn.close.assert_called_once()
    mock_conn.wait_closed.assert_awaited_once()
    assert ssh_client._conn is None
    assert ssh_client._process is None


@pytest.mark.vpn
@pytest.mark.vpn
async def test_aenter_aeexit(ssh_client):
    # Мокаем connect и close
    ssh_client.connect = AsyncMock()
    ssh_client.close = AsyncMock()

    # Тест __aenter__
    async with ssh_client as client:
        ssh_client.connect.assert_awaited_once()
        assert client is ssh_client

    # Тест __aexit__
    ssh_client.close.assert_awaited_once()
