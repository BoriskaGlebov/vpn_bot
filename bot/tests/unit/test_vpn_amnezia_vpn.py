from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_save_wg_config_amneziavpn(ssh_client_vpn):
    ssh_client_vpn._generate_wg_config = AsyncMock(
        return_value="[Interface]\nAddress=10.0.0.3/32"
    )

    with patch(
        "bot.vpn.utils.amnezia_vpn.aiofiles.open", create=True
    ) as mock_aiofiles_open:
        mock_file = AsyncMock()
        mock_aiofiles_open.return_value.__aenter__.return_value = mock_file

        filename = "user_config"
        result = await ssh_client_vpn._save_wg_config(
            filename=filename,
            new_ip="10.0.0.3/32",
            private_key="PRIVATE_KEY",
            pub_server_key="PUB_KEY",
            preshared_key="PSK_KEY",
        )

        assert isinstance(result, Path)
        assert result.suffix == ".vpn"

        mock_aiofiles_open.assert_called_once_with(result, "w")

        written_text = "".join(call.args[0] for call in mock_file.write.call_args_list)
        assert written_text.startswith("vpn://")
        assert "vpn://" in written_text
        result.unlink(missing_ok=True)
