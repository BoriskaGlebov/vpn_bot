from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_current_user, get_session
from api.payment.dependencies import get_payment_service
from api.payment.model import PaymentSource, PaymentStatus
from api.payment.router import router
from shared.enums.admin_enum import RoleEnum


# ------------------
# APP
# ------------------
@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


class FakeRole:
    def __init__(self):
        self.name = RoleEnum.ADMIN.value


# ------------------
# USER (минимальный stub)
# ------------------
class FakeUser:
    def __init__(self):
        self.id = 1
        self.telegram_id = 123456789
        self.username = "test_user"
        self.role = FakeRole()


@pytest.fixture
def user():
    return FakeUser()


# ------------------
# SERVICE MOCK
# ------------------
@pytest.fixture
def payment_service_mock():
    return AsyncMock()


# ------------------
# SESSION MOCK
# ------------------
@pytest.fixture
def session_mock():
    return AsyncMock()


# ------------------
# DEPENDENCY OVERRIDES
# ------------------
@pytest.fixture
def overrides(app, payment_service_mock, user, session_mock):

    app.dependency_overrides[get_payment_service] = lambda: payment_service_mock
    app.dependency_overrides[get_current_user] = lambda: user
    # app.dependency_overrides[check_admin_role]=lambda :user
    app.dependency_overrides[get_session] = lambda: session_mock

    yield

    app.dependency_overrides.clear()


# ------------------
# CLIENT
# ------------------
@pytest.fixture
async def client(app, overrides):
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_transaction(client, payment_service_mock, user, session_mock):

    # мок ответа сервиса (ВАЖНО: должен соответствовать SPaymentTransactionResponse)
    payment_service_mock.create_transaction.return_value = {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
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

    payment_service_mock.get_by_gateway_id.return_value = {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
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
        "gateway_transaction_id": "gw_123",
        "confirmed_at": None,
        "paid_at": None,
    }

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

    tx_id = str(uuid4())

    payment_service_mock.attach_provider_payment.return_value = {
        "id": tx_id,
        "user_id": 1,
        "tg_id": 123456789,
        "amount": 1000,
        "currency": "RUB",
        "status": "PENDING",
        "source": "GATEWAY",
        "subscription_months": 1,
        "is_premium": False,
        "is_founder": False,
        "description": None,
        "created_by_admin_id": None,
        "confirmed_by_admin_id": None,
        "gateway_transaction_id": "gw_123",
        "confirmed_at": None,
        "paid_at": None,
    }

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

    tx_id = uuid4()

    payment_service_mock.mark_payment_started.return_value = {
        "id": str(tx_id),
        "user_id": 1,
        "tg_id": 123456789,
        "amount": 1000,
        "currency": "RUB",
        "status": PaymentStatus.PENDING,
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

    tx_id = uuid4()

    payment_service_mock.confirm_payment_flow.return_value = {
        "transaction_res": {
            "id": str(tx_id),
            "user_id": 1,
            "tg_id": 123456789,
            "amount": 1000,
            "currency": "RUB",
            "status": "PAID",
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
        },
        "subscription_res": {
            "id": 1,
            "telegram_id": 123456789,
            "username": "test_user",
            "first_name": None,
            "last_name": None,
            "has_used_trial": False,
            "role": {
                "id": 1,
                "name": "ADMIN",
            },
            "subscriptions": [],
            "vpn_configs": [],
            "current_subscription": None,
        },
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
    print(response.text)

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

    tx_id = uuid4()

    payment_service_mock.confirm_payment_flow.return_value = {
        "transaction_res": {
            "id": str(tx_id),
            "user_id": 1,
            "tg_id": 123456789,
            "amount": 1000,
            "currency": "RUB",
            "status": "PAID",
            "source": "GATEWAY",
            "subscription_months": 1,
            "is_premium": False,
            "is_founder": False,
            "description": None,
            "created_by_admin_id": None,
            "confirmed_by_admin_id": None,
            "gateway_transaction_id": "gw_123",
            "confirmed_at": None,
            "paid_at": None,
        },
        "subscription_res": {
            "id": 1,
            "telegram_id": 123456789,
            "username": "test_user",
            "first_name": None,
            "last_name": None,
            "has_used_trial": False,
            "role": {
                "id": 1,
                "name": "USER",
            },
            "subscriptions": [],
            "vpn_configs": [],
            "current_subscription": None,
        },
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

    tx_id = uuid4()

    payment_service_mock.cancel_transaction.return_value = {
        "id": str(tx_id),
        "user_id": 1,
        "tg_id": 123456789,
        "amount": 1000,
        "currency": "RUB",
        "status": "CANCELED",
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
