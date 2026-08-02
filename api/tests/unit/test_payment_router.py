"""Контрактные тесты роутера api/payment.

Роутер поднимается изолированно (без остального api.main.app), сервис и сессия
подменяются моками — проверяется только HTTP-контракт: маршрутизация, коды
статусов, сериализация ответа и то, что параметры запроса доходят до сервиса
в ожидаемом виде.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.core.dependencies import get_current_user, get_session, verify_internal_secret
from api.payment.dependencies import get_payment_service
from api.payment.model import PaymentSource, PaymentStatus
from api.payment.router import router
from shared.enums.admin_enum import RoleEnum


def make_transaction_payload(**overrides) -> dict:
    """dict, соответствующий SPaymentTransactionResponse, с полями по умолчанию."""
    payload = {
        "id": str(uuid4()),
        "user_id": 1,
        "tg_id": 123456789,
        "amount": 1000,
        "currency": "RUB",
        "status": "PENDING",
        "source": "MANUAL",
        "subscription_months": 1,
        "is_premium": False,
        "is_founder": False,
        "description": None,
        "created_by_admin_id": None,
        "confirmed_by_admin_id": None,
        "gateway_transaction_id": None,
        "confirmed_at": None,
        "paid_at": None,
    }
    payload.update(overrides)
    return payload


def make_subscription_payload(**overrides) -> dict:
    """dict, соответствующий SUserOut, для confirm_payment_flow-ответов."""
    payload = {
        "id": 1,
        "telegram_id": 123456789,
        "username": "test_user",
        "first_name": None,
        "last_name": None,
        "has_used_trial": False,
        "role": {"id": 1, "name": "USER"},
        "subscriptions": [],
        "vpn_configs": [],
        "current_subscription": None,
    }
    payload.update(overrides)
    return payload


class FakeUser:
    """Минимальный stub текущего пользователя."""

    def __init__(self):
        self.id = 1
        self.telegram_id = 123456789
        self.username = "test_user"
        self.role = type("FakeRole", (), {"name": RoleEnum.ADMIN.value})()


@pytest.fixture
def app():
    """Изолированный FastAPI, содержащий только payment router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def user():
    return FakeUser()


@pytest.fixture
def payment_service_mock():
    return AsyncMock()


@pytest.fixture
def session_mock():
    return AsyncMock()


@pytest.fixture
def overrides(app, payment_service_mock, user, session_mock):
    app.dependency_overrides[get_payment_service] = lambda: payment_service_mock
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session_mock
    app.dependency_overrides[verify_internal_secret] = lambda: None

    yield

    app.dependency_overrides.clear()


@pytest.fixture
async def client(app, overrides):
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_transaction(client, payment_service_mock, user, session_mock):
    """Создание транзакции: тело запроса и авторизованный пользователь доходят до сервиса."""
    payment_service_mock.create_transaction.return_value = make_transaction_payload()

    payload = {
        "amount": 1000,
        "currency": "RUB",
        "subscription_months": 1,
        "is_premium": False,
        "is_founder": False,
        "description": None,
    }

    response = await client.post("/payment/transaction", json=payload)

    assert response.status_code == 201

    payment_service_mock.create_transaction.assert_awaited_once()

    _, kwargs = payment_service_mock.create_transaction.await_args

    # проверки прокидывания зависимостей
    assert kwargs["session"] == session_mock
    assert kwargs["user_auth"] == user

    # проверка payload (Pydantic модель прилетает уже как объект)
    assert kwargs["transaction"].amount == 1000
    assert kwargs["transaction"].currency == "RUB"
    assert kwargs["transaction"].subscription_months == 1


@pytest.mark.asyncio
async def test_get_by_gateway_id(
    client,
    payment_service_mock,
    session_mock,
):
    """Поиск транзакции по gateway_transaction_id из query-параметра."""
    payment_service_mock.get_by_gateway_id.return_value = make_transaction_payload(
        gateway_transaction_id="gw_123",
    )

    response = await client.get(
        "/payment/transaction",
        params={"gateway_transaction_id": "gw_123"},
    )

    assert response.status_code == 200

    payment_service_mock.get_by_gateway_id.assert_awaited_once()

    _, kwargs = payment_service_mock.get_by_gateway_id.await_args

    assert kwargs["gateway_transaction_id"] == "gw_123"
    assert kwargs["session"] == session_mock


@pytest.mark.asyncio
async def test_attach_provider_payment(
    client,
    payment_service_mock,
    session_mock,
    user,
):
    """Привязка провайдера: transaction_id из пути и тело доходят до сервиса как объект."""
    tx_id = str(uuid4())

    payment_service_mock.attach_provider_payment.return_value = (
        make_transaction_payload(
            id=tx_id,
            source="GATEWAY",
            gateway_transaction_id="gw_123",
        )
    )

    payload = {
        "gateway_transaction_id": "gw_123",
        "gateway_payload": {"order_id": 999},
        "source": "GATEWAY",
    }

    response = await client.post(
        f"/payment/transaction/{tx_id}/provider",
        json=payload,
    )

    assert response.status_code == 200

    payment_service_mock.attach_provider_payment.assert_awaited_once()

    _, kwargs = payment_service_mock.attach_provider_payment.await_args

    assert kwargs["session"] == session_mock
    assert str(kwargs["transaction_id"]) == tx_id

    # payload проверяем как объект Pydantic
    assert kwargs["gateway_info"].gateway_transaction_id == "gw_123"
    assert kwargs["gateway_info"].source == "GATEWAY"


@pytest.mark.asyncio
async def test_mark_payment_started(
    client,
    payment_service_mock,
    session_mock,
    user,
):
    """Пометка начала оплаты по transaction_id из пути."""
    tx_id = uuid4()

    payment_service_mock.mark_payment_started.return_value = make_transaction_payload(
        id=str(tx_id),
        status=PaymentStatus.PENDING,
    )

    response = await client.post(f"/payment/transaction/{tx_id}/paid")

    assert response.status_code == 200

    payment_service_mock.mark_payment_started.assert_awaited_once()

    _, kwargs = payment_service_mock.mark_payment_started.await_args

    assert kwargs["session"] == session_mock
    assert str(kwargs["transaction_id"]) == str(tx_id)


@pytest.mark.asyncio
async def test_admin_confirm_transaction(
    client,
    payment_service_mock,
    session_mock,
):
    """Ручное подтверждение админом: payment_source=MANUAL и admin_id из текущего пользователя."""
    tx_id = uuid4()

    payment_service_mock.confirm_payment_flow.return_value = {
        "transaction_res": make_transaction_payload(id=str(tx_id), status="PAID"),
        "subscription_res": make_subscription_payload(role={"id": 1, "name": "ADMIN"}),
        "referral_res": {
            "success": False,
            "inviter_telegram_id": None,
            "message": "no referral",
        },
    }

    payload = {"id": str(tx_id)}

    response = await client.post(
        "/payment/transaction/admin/confirm",
        json=payload,
    )

    assert response.status_code == 200

    payment_service_mock.confirm_payment_flow.assert_awaited_once()

    _, kwargs = payment_service_mock.confirm_payment_flow.await_args

    assert kwargs["session"] == session_mock

    # body schema
    assert kwargs["data"].id == tx_id

    # enum check
    assert kwargs["payment_source"].value == PaymentSource.MANUAL

    # admin id check
    assert kwargs["admin_id"] == 1


@pytest.mark.asyncio
async def test_webhook_confirm_transaction(
    client,
    payment_service_mock,
    session_mock,
):
    """Подтверждение через webhook: payment_source=GATEWAY, admin_id не участвует."""
    tx_id = uuid4()

    payment_service_mock.confirm_payment_flow.return_value = {
        "transaction_res": make_transaction_payload(
            id=str(tx_id),
            status="PAID",
            source="GATEWAY",
            gateway_transaction_id="gw_123",
        ),
        "subscription_res": make_subscription_payload(),
        "referral_res": {
            "success": True,
            "inviter_telegram_id": 999,
            "message": "bonus granted",
        },
    }

    payload = {"id": str(tx_id)}

    response = await client.post(
        "/payment/transaction/webhook/confirm",
        json=payload,
    )

    assert response.status_code == 200

    payment_service_mock.confirm_payment_flow.assert_awaited_once()

    _, kwargs = payment_service_mock.confirm_payment_flow.await_args

    assert kwargs["session"] == session_mock

    assert kwargs["payment_source"].value == "GATEWAY"

    assert kwargs["data"].id == tx_id


@pytest.mark.asyncio
async def test_cancel_transaction(
    client,
    payment_service_mock,
    session_mock,
    user,
):
    """Отмена транзакции по id из тела запроса."""
    tx_id = uuid4()

    payment_service_mock.cancel_transaction.return_value = make_transaction_payload(
        id=str(tx_id),
        status="CANCELED",
    )

    payload = {"id": str(tx_id)}

    response = await client.post(
        "/payment/transaction/cancel",
        json=payload,
    )

    assert response.status_code == 200

    payment_service_mock.cancel_transaction.assert_awaited_once()

    _, kwargs = payment_service_mock.cancel_transaction.await_args

    assert kwargs["session"] == session_mock

    # body schema
    assert kwargs["data"].id == tx_id


@pytest.mark.asyncio
async def test_webhook_cancel_transaction(
    client,
    payment_service_mock,
    session_mock,
):
    """Отмена транзакции по вебхуку платёжного провайдера (без Telegram-контекста
    пользователя — см. в api/payment/router.py).
    """
    tx_id = uuid4()

    payment_service_mock.cancel_transaction.return_value = make_transaction_payload(
        id=str(tx_id),
        status="CANCELED",
        source="GATEWAY",
    )

    payload = {"id": str(tx_id)}

    response = await client.post(
        "/payment/transaction/webhook/cancel",
        json=payload,
    )

    assert response.status_code == 200

    payment_service_mock.cancel_transaction.assert_awaited_once()

    _, kwargs = payment_service_mock.cancel_transaction.await_args

    assert kwargs["session"] == session_mock
    assert kwargs["data"].id == tx_id
