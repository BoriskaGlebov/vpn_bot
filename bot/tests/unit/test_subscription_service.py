from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot.subscription.schemas import SSubscriptionCheck, SSubscriptionInfo, SVPNConfig
from bot.subscription.services import SubscriptionService
from bot.users.schemas import SUserOut
from bot.vpn.utils.x_ray_exceptions import ThreeXUIRequestError
from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import TrialStatus


@pytest.fixture
def adapter_mock():
    return AsyncMock()


@pytest.fixture
def service(adapter_mock, mock_users_adapter, moc_payment_adapter, mock_vpn_service):
    return SubscriptionService(
        adapter_mock, mock_users_adapter, moc_payment_adapter, mock_vpn_service
    )


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
async def test_confirm_transaction_extends_xray(
    service, moc_payment_adapter, mock_vpn_service, user_out
):
    confirm_result = SimpleNamespace(
        transaction_res=Mock(), subscription_res=user_out, referral_res=Mock()
    )
    moc_payment_adapter.confirm_transaction.return_value = confirm_result

    result = await service.confirm_transaction(transaction_id="tx-1")

    assert result is confirm_result
    moc_payment_adapter.confirm_transaction.assert_awaited_once_with(
        transaction_id="tx-1"
    )
    mock_vpn_service.extend_user_xray_subscription.assert_awaited_once_with(
        user=user_out
    )


@pytest.mark.asyncio
async def test_webhook_confirm_transaction_extends_xray(
    service, moc_payment_adapter, mock_vpn_service, user_out
):
    confirm_result = SimpleNamespace(
        transaction_res=Mock(), subscription_res=user_out, referral_res=Mock()
    )
    moc_payment_adapter.webhook_confirm_transaction.return_value = confirm_result

    result = await service.webhook_confirm_transaction(transaction_id="tx-2")

    assert result is confirm_result
    moc_payment_adapter.webhook_confirm_transaction.assert_awaited_once_with(
        transaction_id="tx-2"
    )
    mock_vpn_service.extend_user_xray_subscription.assert_awaited_once_with(
        user=user_out
    )


@pytest.mark.asyncio
async def test_confirm_transaction_xray_error_does_not_break_payment_flow(
    service, moc_payment_adapter, mock_vpn_service, user_out
):
    """Ошибка продления на 3x-ui не должна ломать уже подтверждённую оплату."""
    confirm_result = SimpleNamespace(
        transaction_res=Mock(), subscription_res=user_out, referral_res=Mock()
    )
    moc_payment_adapter.confirm_transaction.return_value = confirm_result
    mock_vpn_service.extend_user_xray_subscription.side_effect = ThreeXUIRequestError(
        action="update_client", reason="boom"
    )

    result = await service.confirm_transaction(transaction_id="tx-1")

    assert result is confirm_result


@pytest.mark.asyncio
async def test_get_subscription_info_no_subscription(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    payment_adapter = mocker.AsyncMock()
    vpn_service = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="no_subscription",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = SubscriptionService(
        api_adapter, user_adapter, payment_adapter, vpn_service
    )

    result = await service.get_subscription_info(123)

    assert result == "У вас нет подписки."


@pytest.mark.asyncio
async def test_get_subscription_info_active(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    payment_adapter = mocker.AsyncMock()
    vpn_service = mocker.AsyncMock()

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

    service = SubscriptionService(
        api_adapter, user_adapter, payment_adapter, vpn_service
    )

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
    payment_adapter = mocker.AsyncMock()
    vpn_service = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="inactive",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = SubscriptionService(
        api_adapter, user_adapter, payment_adapter, vpn_service
    )

    result = await service.get_subscription_info(123)

    assert "🔒 Неактивна" in result
    assert "Бесконечность не предел" in result


@pytest.mark.asyncio
async def test_is_subscription_active_true(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    payment_adapter = mocker.AsyncMock()
    vpn_service = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="active",
        subscription_type="premium",
        remaining="10 дней",
        configs=[],
        end_date=datetime(2026, 1, 1),
    )

    service = SubscriptionService(
        api_adapter, user_adapter, payment_adapter, vpn_service
    )

    assert await service.is_subscription_active(123) is True


@pytest.mark.asyncio
async def test_is_subscription_active_false(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    payment_adapter = mocker.AsyncMock()
    vpn_service = mocker.AsyncMock()

    api_adapter.get_subscription_info.return_value = SSubscriptionInfo(
        status="inactive",
        subscription_type=None,
        remaining="0",
        configs=[],
        end_date=None,
    )

    service = SubscriptionService(
        api_adapter, user_adapter, payment_adapter, vpn_service
    )

    assert await service.is_subscription_active(123) is False
