from unittest.mock import AsyncMock

import pytest

from api.app_error.base_error import UserNotFoundError
from api.users.schemas import SRoleOut, SUserOut
from shared.enums.admin_enum import RoleEnum


class FakeAdminService:
    def __init__(self):
        self.get_user_by_telegram_id = None
        self.get_users_by_filter = None
        self.change_user_role = None
        self.extend_user_subscription = None


@pytest.fixture
def mock_service():
    return FakeAdminService()


def make_user():
    return SUserOut(
        id=1,
        telegram_id=123,
        username="test",
        first_name="Test",
        last_name="User",
        has_used_trial=False,
        role=SRoleOut(id=1, name="admin", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )


def test_get_user_success(client, mock_service):
    """Пользователь найден по telegram_id -> 200 с его данными."""
    user = make_user()

    mock_service.get_user_by_telegram_id = AsyncMock(return_value=user)

    response = client.get("/admin/users/123")

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 123


def test_get_user_not_found(client, mock_service):
    """Сервис бросает UserNotFoundError -> 404."""
    mock_service.get_user_by_telegram_id = AsyncMock(
        side_effect=UserNotFoundError(tg_id=123)
    )

    response = client.get("/admin/users/123")

    assert response.status_code == 404


def test_get_users(client, mock_service):
    """Список пользователей по фильтру роли."""
    users = [make_user(), make_user()]

    mock_service.get_users_by_filter = AsyncMock(return_value=users)

    response = client.get("/admin/users", params={"filter_type": RoleEnum.ADMIN.value})

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_change_user_role_success(client, mock_service):
    """Смена роли пользователя -> 200 с обновлённой ролью."""
    user = make_user()

    mock_service.change_user_role = AsyncMock(return_value=user)

    payload = {
        "telegram_id": 123,
        "role_name": "admin",
    }

    response = client.patch("/admin/users/role", json=payload)

    assert response.status_code == 200
    assert response.json()["role"]["name"] == "admin"


def test_change_user_role_not_found(client, mock_service):
    """Пользователь не найден -> 404."""
    mock_service.change_user_role = AsyncMock(side_effect=UserNotFoundError(tg_id=123))

    payload = {
        "telegram_id": 123,
        "role_name": "admin",
    }

    response = client.patch("/admin/users/role", json=payload)

    assert response.status_code == 404


def test_extend_subscription_success(client, mock_service):
    """Продление подписки администратором -> 200 с данными пользователя."""
    user = make_user()

    mock_service.extend_user_subscription = AsyncMock(return_value=user)

    payload = {
        "telegram_id": 123,
        "months": 3,
    }

    response = client.patch("/admin/users/subscription", json=payload)

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 123


def test_extend_subscription_validation_error(client):
    """months=0 не проходит валидацию схемы (ge=1) -> 422."""
    payload = {
        "telegram_id": 123,
        "months": 0,  # invalid (ge=1)
    }

    response = client.patch("/admin/users/subscription", json=payload)

    assert response.status_code == 422


def test_get_income_success(client):
    """Доход за явно указанный год."""
    response = client.get("/admin/analytics/income", params={"year": 2026})

    assert response.status_code == 200
    assert response.json()["year_income"] == 1500


def test_get_income_current_year(client):
    """Год не передан -> используется текущий (по FakePaymentService всегда 1500)."""
    response = client.get("/admin/analytics/income")

    assert response.status_code == 200
    assert response.json()["year_income"] == 1500


def test_get_income_validation_error(client):
    """Нечисловой year -> 422."""
    response = client.get(
        "/admin/analytics/income",
        params={"year": "invalid"},
    )

    assert response.status_code == 422
