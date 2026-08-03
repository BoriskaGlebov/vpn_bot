from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment.dto import PaymentStatus, PaymentWebhookDTO
from bot.payment.services import PaymentWebhookService


@pytest.fixture
def payment_service_mock():
    return AsyncMock()


@pytest.fixture
def subscription_service_mock():
    return AsyncMock()


@pytest.fixture
def notification_service_mock():
    return AsyncMock()


@pytest.fixture
def webhook_service(
    payment_service_mock, subscription_service_mock, notification_service_mock
):
    return PaymentWebhookService(
        payment_service=payment_service_mock,
        subscription_service=subscription_service_mock,
        notification_service=notification_service_mock,
    )


@pytest.mark.asyncio
async def test_handle_event_paid_confirms_via_subscription_service(
    webhook_service, payment_service_mock, subscription_service_mock
):
    """При успешной оплате подтверждение (и продление XRay-конфигов) должно
    идти через `subscription_service`, а не напрямую через `payment_service` —
    иначе `SubscriptionService._extend_xray_after_payment` не вызывается и
    XRay-конфиги на панели 3x-ui остаются с истёкшим сроком.
    """
    tx = SimpleNamespace(id="tx-1", tg_id=123, amount=1000)
    payment_service_mock.get_by_gateway_id.return_value = tx
    confirm = SimpleNamespace(transaction_res=tx)
    subscription_service_mock.webhook_confirm_transaction.return_value = confirm

    event = PaymentWebhookDTO(
        provider_payment_id="prov-1",
        status=PaymentStatus.PAID,
        raw_data={},
    )

    await webhook_service.handle_event(event)

    subscription_service_mock.webhook_confirm_transaction.assert_awaited_once_with(
        tx.id
    )
    payment_service_mock.webhook_confirm_transaction.assert_not_called()
    webhook_service.notification_service.notify_payment_confirmed.assert_awaited_once_with(
        confirm, provider_name=payment_service_mock.provider.provider_name
    )


@pytest.mark.asyncio
async def test_handle_event_failed_cancels_transaction(
    webhook_service, payment_service_mock, subscription_service_mock
):
    tx = SimpleNamespace(id="tx-2", tg_id=123, amount=1000)
    payment_service_mock.get_by_gateway_id.return_value = tx

    event = PaymentWebhookDTO(
        provider_payment_id="prov-2",
        status=PaymentStatus.FAILED,
        raw_data={"status": "CANCELED"},
    )

    await webhook_service.handle_event(event)

    payment_service_mock.webhook_cancel_transaction.assert_awaited_once_with(tx.id)
    subscription_service_mock.webhook_confirm_transaction.assert_not_called()
    webhook_service.notification_service.notify_payment_failed.assert_awaited_once_with(
        transaction_id=tx.id, tg_id=tx.tg_id, is_chargeback=False
    )


@pytest.mark.asyncio
async def test_handle_event_chargebacked_flags_admin_alert(
    webhook_service, payment_service_mock
):
    """CHARGEBACKED должен помечаться отдельно от обычного CANCELED — это
    возврат уже полученных денег, требующий внимания администратора.
    """
    tx = SimpleNamespace(id="tx-3", tg_id=123, amount=1000)
    payment_service_mock.get_by_gateway_id.return_value = tx

    event = PaymentWebhookDTO(
        provider_payment_id="prov-3",
        status=PaymentStatus.FAILED,
        raw_data={"status": "CHARGEBACKED"},
    )

    await webhook_service.handle_event(event)

    webhook_service.notification_service.notify_payment_failed.assert_awaited_once_with(
        transaction_id=tx.id, tg_id=tx.tg_id, is_chargeback=True
    )
