from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from bot.subscription.schemas import SSubscriptionCheck, SSubscriptionInfo, SVPNConfig
from bot.subscription.services import SubscriptionService
from bot.users.schemas import SUserOut
from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import TrialStatus


@pytest.fixture
def adapter_mock():
    return AsyncMock()


@pytest.fixture
def service(adapter_mock, mock_users_adapter):
    return SubscriptionService(adapter_mock, mock_users_adapter)


@pytest.mark.asyncio
async def test_check_premium(service, adapter_mock):
    adapter_mock.check_premium.return_value = SSubscriptionCheck(
        premium=True, role=RoleEnum.USER, is_active=True, used_trial=True
    )

    result = await service.check_premium(tg_id=123)

    assert result == (True, RoleEnum.USER, True, True)

    adapter_mock.check_premium.assert_awaited_once_with(tg_id=123)


@pytest.mark.asyncio
async def test_start_trial_subscription(service, adapter_mock):
    adapter_mock.activate_trial.return_value = (
        {"status": TrialStatus.STARTED},
        201,
    )

    await service.start_trial_subscription(tg_id=123, days=7)

    adapter_mock.activate_trial.assert_awaited_once_with(
        tg_id=123,
        days=7,
    )


@pytest.mark.asyncio
async def test_activate_paid_subscription(service, adapter_mock, user_out):
    adapter_mock.activate_paid.return_value = user_out.model_dump()

    result = await service.activate_paid_subscription(
        tg_id=user_out.telegram_id,
        months=3,
        premium=True,
    )

    result = SUserOut.model_validate(result)

    assert result.model_dump() == user_out.model_dump()

    adapter_mock.activate_paid.assert_awaited_once_with(
        tg_id=user_out.telegram_id,
        months=3,
        premium=True,
    )


@pytest.mark.asyncio
async def test_get_subscription_info_no_subscription(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="no_subscription",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = SubscriptionService(api_adapter, user_adapter)

    result = await service.get_subscription_info(123)

    assert result == "У вас нет подписки."


@pytest.mark.asyncio
async def test_get_subscription_info_active(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="active",
        subscription_type="premium",
        remaining="10 дней",
        configs=[
            SVPNConfig(file_name="conf1"),
            SVPNConfig(file_name="conf2"),
        ],
        end_date=datetime(2026, 1, 1),
    )

    service = SubscriptionService(api_adapter, user_adapter)

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

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="inactive",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = SubscriptionService(api_adapter, user_adapter)

    result = await service.get_subscription_info(123)

    assert "🔒 Неактивна" in result
    assert "Бесконечность не предел" in result
