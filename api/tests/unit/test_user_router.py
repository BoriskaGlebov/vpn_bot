from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.app_error.api_error import APIError
from api.core.dependencies import (
    get_current_user,
    get_session,
    verify_internal_secret,
)
from api.core.exceptions.handlers.http import api_error_handler
from api.tests.conftest import fake_user
from api.users.dependencies import get_user_service
from api.users.router import router as users_router
from api.users.schemas import SRoleOut, SUserOut, SUserWithReferralStats
from api.users.services import UserService
from shared.enums.admin_enum import RoleEnum


@pytest.fixture
def service_mock():
    return MagicMock(spec=UserService)


@pytest.fixture
def client(make_client, service_mock):
    """TestClient с переопределёнными зависимостями роутера пользователей."""
    with make_client(
        {
            get_user_service: lambda: service_mock,
            get_session: lambda: AsyncMock(),
            get_current_user: fake_user,
            verify_internal_secret: lambda: None,
        }
    ) as c:
        yield c


@pytest.fixture
def app_no_secret_override(service_mock):
    """Тот же роутер пользователей, но БЕЗ переопределения verify_internal_secret.

    Используется, чтобы доказать, что /users/register сам защищён зависимостью,
    а не просто что verify_internal_secret умеет бросать исключение — регрессия
    на дыру, где этот роут был единственным изменяющим в api/ без какой-либо
    авторизации (#230).
    """
    isolated_app = FastAPI()
    isolated_app.include_router(users_router)
    isolated_app.add_exception_handler(APIError, api_error_handler)
    isolated_app.dependency_overrides[get_user_service] = lambda: service_mock
    isolated_app.dependency_overrides[get_session] = lambda: AsyncMock()
    return isolated_app


@pytest.fixture
async def client_no_secret(app_no_secret_override):
    transport = ASGITransport(app=app_no_secret_override)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_register_user_rejects_missing_internal_secret(
    client_no_secret, service_mock
):
    """Без X-Internal-Secret регистрация отклоняется, не выполняя запрос."""
    payload = {"telegram_id": 123, "username": "test"}

    response = await client_no_secret.post("/users/register", json=payload)

    assert response.status_code == 401
    service_mock.register_or_get_user.assert_not_called()


@pytest.mark.asyncio
async def test_register_user_rejects_wrong_internal_secret(
    client_no_secret, service_mock
):
    """Неверный (не пустой) X-Internal-Secret тоже отклоняется."""
    payload = {"telegram_id": 123, "username": "test"}

    response = await client_no_secret.post(
        "/users/register",
        json=payload,
        headers={"X-Internal-Secret": "not-the-real-secret"},
    )

    assert response.status_code == 401
    service_mock.register_or_get_user.assert_not_called()


@pytest.mark.asyncio
async def test_register_user_created(client, service_mock):
    """Новый пользователь регистрируется, ответ 201 с telegram_id."""
    service_mock.register_or_get_user.return_value = (
        SUserOut(
            id=1,
            telegram_id=123,
            username="test",
            first_name="Test",
            last_name="User",
            role=SRoleOut(name=RoleEnum.USER, id=1, description="ПОользователь"),
            subscriptions=[],
            has_used_trial=False,
        ),
        True,
    )

    payload = {
        "telegram_id": 123,
        "username": "test",
        "first_name": "Test",
        "last_name": "User",
    }

    response = client.post("/api/users/register", json=payload)

    assert response.status_code == 201
    assert response.json()["telegram_id"] == 123

    service_mock.register_or_get_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_user_existing(client, service_mock):
    """Повторная регистрация уже известного пользователя возвращает 200 (не 201)."""
    service_mock.register_or_get_user.return_value = (
        {
            "telegram_id": 123,
            "id": 1234,
            "username": "test",
            "has_used_trial": False,
            "role": SRoleOut(name=RoleEnum.USER, id=1, description="ПОользователь"),
        },
        False,
    )

    response = client.post(
        "/api/users/register",
        json={
            "telegram_id": 123,
            "username": "test",
            "first_name": "Test",
            "last_name": "User",
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_user_referrals_success(client, service_mock):
    """Возвращает пользователя вместе с реферальной статистикой."""
    service_mock.get_user_with_referrals.return_value = SUserWithReferralStats(
        id=1,
        telegram_id=123,
        username="test",
        first_name="Test",
        last_name="User",
        has_used_trial=False,
        role=SRoleOut(name=RoleEnum.USER, id=1, description="Пользователь"),
        referrals_count=5,
        paid_referrals_count=2,
        referral_conversion=0.4,
    )

    response = client.get("/api/users/123/referrals")

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 123

    service_mock.get_user_with_referrals.assert_awaited_once_with(
        session=ANY,
        telegram_id=123,
    )


@pytest.mark.asyncio
async def test_get_user_referrals_not_found(client, service_mock):
    """Сервис вернул None -> ответ об ошибке (404/500 в зависимости от хендлера)."""
    service_mock.get_user_with_referrals.return_value = None

    response = client.get("/api/users/999/referrals")

    assert response.status_code in (404, 500)  # зависит от exception handler
