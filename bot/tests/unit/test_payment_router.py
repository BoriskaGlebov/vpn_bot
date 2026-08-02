"""Контрактные тесты для `bot/payment/router.py::build_payment_router`.

Роутер поднимается изолированно (без остального `bot.main.app`), провайдер и
`payment_webhook_service` подменяются моками, `send_to_admins` патчится —
проверяется HTTP-контракт эндпоинта `/payment-webhook`: коды статусов и то,
что каждая ветка обработки (успех / неверная подпись / битое тело / гонка
отмена-vs-вебхук / неожиданная ошибка) действительно ведёт себя так, как
описано в докстринге `payment_webhook` — это единственный денежный webhook
проекта, доступный извне без Telegram-контекста.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bot.app_error.api_error import APIClientConflictError
from bot.app_error.schema import ErrorDetail
from bot.core.config import settings_bot
from bot.payment.dto import PaymentStatus, PaymentWebhookDTO
from bot.payment.router import build_payment_router

m_subscription = settings_bot.messages.modes.subscription


@pytest.fixture
def payment_service_mock():
    service = Mock()
    service.provider = AsyncMock()
    return service


@pytest.fixture
def payment_webhook_service_mock():
    return AsyncMock()


@pytest.fixture
def bot_mock():
    return AsyncMock()


@pytest.fixture
def app(payment_service_mock, payment_webhook_service_mock, bot_mock):
    router = build_payment_router(
        bot=bot_mock,
        logger=Mock(),
        payment_service=payment_service_mock,
        payment_webhook_service=payment_webhook_service_mock,
        m_subscription=m_subscription,
    )
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def make_event(status: PaymentStatus = PaymentStatus.PAID) -> PaymentWebhookDTO:
    return PaymentWebhookDTO(
        provider_payment_id="prov-123",
        status=status,
        raw_data={"id": "prov-123", "status": "CONFIRMED"},
    )


@pytest.mark.asyncio
async def test_empty_body_returns_200_without_touching_provider(
    client, payment_service_mock, payment_webhook_service_mock
):
    """Пустое тело — штатный keep-alive/проверочный запрос, не настоящий вебхук.

    Не должен доходить ни до проверки подписи, ни до обработки события —
    иначе легко превратить "пустой пинг" в ложное 403/500 в логах.
    """
    response = await client.post("/payment-webhook", content=b"")

    assert response.status_code == 200
    payment_service_mock.provider.verify_webhook.assert_not_called()
    payment_webhook_service_mock.handle_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_signature_returns_403_and_stops_processing(
    client, payment_service_mock, payment_webhook_service_mock
):
    """Провал проверки подписи должен давать 403 и не идти дальше в обработку.

    Регрессия на прежний баг: до подключения verify_webhook подделанный
    запрос с правдоподобным JSON обрабатывался как настоящий платёж.
    """
    payment_service_mock.provider.verify_webhook.return_value = False

    response = await client.post("/payment-webhook", json={"id": "x"})

    assert response.status_code == 403
    payment_service_mock.provider.parse_webhook.assert_not_called()
    payment_webhook_service_mock.handle_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_unparsable_body_returns_400(client, payment_service_mock):
    """Подпись верна, но тело не парсится (битый JSON/неожиданный формат) — 400, не 500.

    400, а не 500: это ошибка запроса провайдера, а не сбой на нашей стороне —
    провайдер не должен ретраить бесконечно то, что в принципе не распарсится.
    """
    payment_service_mock.provider.verify_webhook.return_value = True
    payment_service_mock.provider.parse_webhook.side_effect = ValueError("bad json")

    response = await client.post("/payment-webhook", content=b"not-json")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_successful_event_is_handled_and_returns_200(
    client, payment_service_mock, payment_webhook_service_mock
):
    """Штатный успешный вебхук доходит до handle_event с разобранным событием."""
    payment_service_mock.provider.verify_webhook.return_value = True
    event = make_event(PaymentStatus.PAID)
    payment_service_mock.provider.parse_webhook.return_value = event

    response = await client.post("/payment-webhook", json={"id": "prov-123"})

    assert response.status_code == 200
    payment_webhook_service_mock.handle_event.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_conflict_on_already_paid_is_idempotent_no_admin_alert(
    client, payment_service_mock, payment_webhook_service_mock, mocker
):
    """Повторная доставка уже обработанного платежа — 200 без тревоги админам.

    Platega повторяет вебхук до 3 раз, если не получила 200 вовремя — это
    ожидаемое поведение, не инцидент, и не должно спамить админов.
    """
    send_to_admins_mock = mocker.patch("bot.payment.router.send_to_admins")

    payment_service_mock.provider.verify_webhook.return_value = True
    payment_service_mock.provider.parse_webhook.return_value = make_event()
    payment_webhook_service_mock.handle_event.side_effect = APIClientConflictError(
        409,
        ErrorDetail(
            code="payment_already_processed",
            message="already processed",
            details={"status": "PAID", "transaction_id": "tx-1"},
        ),
    )

    response = await client.post("/payment-webhook", json={"id": "prov-123"})

    assert response.status_code == 200
    send_to_admins_mock.assert_not_called()


@pytest.mark.asyncio
async def test_conflict_on_canceled_transaction_alerts_admins(
    client, payment_service_mock, payment_webhook_service_mock, bot_mock, mocker
):
    """Вебхук подтвердил оплату уже отменённой транзакции — гонка, деньги под вопросом.

    В отличие от повторной доставки PAID (см. тест выше) — это реальный
    сигнал для ручной проверки: деньги могли поступить, а услуга не
    предоставлена. Должен уйти алерт админам с id транзакции и статусом.
    """
    send_to_admins_mock = mocker.patch(
        "bot.payment.router.send_to_admins", new=AsyncMock()
    )

    payment_service_mock.provider.verify_webhook.return_value = True
    payment_service_mock.provider.parse_webhook.return_value = make_event()
    payment_webhook_service_mock.handle_event.side_effect = APIClientConflictError(
        409,
        ErrorDetail(
            code="payment_already_processed",
            message="already processed",
            details={"status": "CANCELED", "transaction_id": "tx-42"},
        ),
    )

    response = await client.post("/payment-webhook", json={"id": "prov-123"})

    assert response.status_code == 200
    send_to_admins_mock.assert_awaited_once()
    _, kwargs = send_to_admins_mock.await_args
    assert kwargs["bot"] is bot_mock
    assert "tx-42" in kwargs["message_text"]
    assert "CANCELED" in kwargs["message_text"]


@pytest.mark.asyncio
async def test_unexpected_error_returns_500_and_alerts_admins(
    client, payment_service_mock, payment_webhook_service_mock, mocker
):
    """Неожиданная ошибка обработки — 500 (провайдер повторит доставку) + алерт админам.

    500 — намеренно: Platega ретраит недоставленные вебхуки, а без алерта
    админам никто не узнал бы, что подтверждение оплаты не прошло.
    """
    send_to_admins_mock = mocker.patch(
        "bot.payment.router.send_to_admins", new=AsyncMock()
    )

    payment_service_mock.provider.verify_webhook.return_value = True
    payment_service_mock.provider.parse_webhook.return_value = make_event()
    payment_webhook_service_mock.handle_event.side_effect = RuntimeError("db is down")

    response = await client.post("/payment-webhook", json={"id": "prov-123"})

    assert response.status_code == 500
    send_to_admins_mock.assert_awaited_once()
    _, kwargs = send_to_admins_mock.await_args
    assert "prov-123" in kwargs["message_text"]
