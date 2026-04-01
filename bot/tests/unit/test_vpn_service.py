from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.app_error.base_error import VPNLimitError
from bot.users.schemas import SUser
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNConfig,
    SVPNSubscriptionInfo,
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


@pytest.mark.asyncio
async def test_get_subscription_info_no_subscription(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SVPNSubscriptionInfo(
        status="no_subscription",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = VPNService(api_adapter, user_adapter)

    result = await service.get_subscription_info(123)

    assert result == "У вас нет подписки."


@pytest.mark.asyncio
async def test_get_subscription_info_active(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SVPNSubscriptionInfo(
        status="active",
        subscription_type="premium",
        remaining="10 дней",
        configs=[
            SVPNConfig(file_name="conf1"),
            SVPNConfig(file_name="conf2"),
        ],
        end_date=datetime(2026, 1, 1),
    )

    service = VPNService(api_adapter, user_adapter)

    result = await service.get_subscription_info(123)

    assert "✅ Активна" in result
    assert "<b>PREMIUM</b>" in result
    assert "10 дней до (2026-01-01)" in result
    assert "📌 conf1" in result
    assert "📌 conf2" in result


@pytest.mark.asyncio
async def test_get_subscription_info_inactive_no_end_date(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SVPNSubscriptionInfo(
        status="inactive",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = VPNService(api_adapter, user_adapter)

    result = await service.get_subscription_info(123)

    assert "🔒 Неактивна" in result
    assert "Бесконечность не предел" in result
