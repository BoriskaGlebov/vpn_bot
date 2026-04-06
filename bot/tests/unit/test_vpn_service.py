from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.app_error.base_error import VPNLimitError
from bot.users.schemas import SUser
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
)
from bot.vpn.services import VPNService


@pytest.mark.asyncio
async def test_generate_user_config_success(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    ssh_client = mocker.AsyncMock()

    tg_user = SimpleNamespace(id=123)

    api_adapter.check_limit.return_value = SVPNCheckLimitResponse(
        can_add=True,
        limit=5,
        current=1,
    )

    user_adapter.register.return_value = (
        SUser(telegram_id=123, username="testuser"),
        True,
    )

    ssh_client.add_new_user_gen_config.return_value = (
        Path("/tmp/test.conf"),
        "pubkey123",
    )

    service = VPNService(api_adapter, user_adapter)

    file_path, pub_key = await service.generate_user_config(
        tg_user,
        ssh_client,
    )

    assert file_path.name == "test.conf"
    assert pub_key == "pubkey123"

    api_adapter.check_limit.assert_awaited_once_with(tg_id=123)

    user_adapter.register.assert_awaited_once()

    ssh_client.add_new_user_gen_config.assert_awaited_once_with(file_name="testuser")

    api_adapter.add_config.assert_awaited_once_with(
        tg_id=123,
        file_name="test.conf",
        pub_key="pubkey123",
    )


@pytest.mark.asyncio
async def test_generate_user_config_limit_reached(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    ssh_client = mocker.AsyncMock()

    tg_user = SimpleNamespace(id=123)

    api_adapter.check_limit.return_value = SVPNCheckLimitResponse(
        can_add=False,
        limit=1,
        current=1,
    )

    user_adapter.register.return_value = (
        SUser(telegram_id=123, username="testuser"),
        True,
    )

    service = VPNService(api_adapter, user_adapter)

    with pytest.raises(VPNLimitError) as exc:
        await service.generate_user_config(tg_user, ssh_client)

    err = exc.value
    assert err.user_id == 123
    assert err.limit == 1

    ssh_client.add_new_user_gen_config.assert_not_called()
    api_adapter.add_config.assert_not_called()
