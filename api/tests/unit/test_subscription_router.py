from unittest.mock import AsyncMock, MagicMock

import pytest

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_current_user, get_session
from api.subscription.dependencies import get_subscription_service
from api.subscription.services import SubscriptionService
from api.tests.conftest import fake_admin, fake_user
from api.users.schemas import SRoleOut
from shared.enums.admin_enum import RoleEnum


@pytest.fixture
def mock_service():
    return MagicMock(spec=SubscriptionService)


@pytest.fixture
def client(make_client, mock_service):
    """TestClient с переопределёнными зависимостями роутера подписок."""
    with make_client(
        {
            get_subscription_service: lambda: mock_service,
            get_session: lambda: AsyncMock(),
            get_current_user: fake_user,
            check_admin_role: fake_admin,
        }
    ) as c:
        yield c


def test_check_premium(client, mock_service):
    """Возвращает статус премиума/активности подписки пользователя."""
    mock_service.check_premium = AsyncMock(
        return_value=(True, RoleEnum.USER, True, False)
    )

    response = client.get("/api/subscriptions/check/premium?tg_id=123")

    assert response.status_code == 200
    data = response.json()

    assert data["premium"] is True
    assert data["role"] == RoleEnum.USER
    assert data["is_active"] is True
    assert data["used_trial"] is False

    mock_service.check_premium.assert_awaited_once()


def test_start_trial(client, mock_service):
    """Активация триала возвращает 201 и статус trial_started."""
    mock_service.start_trial_subscription = AsyncMock(return_value=None)

    payload = {"tg_id": 123, "days": 10}

    response = client.post("/api/subscriptions/trial/activate", json=payload)

    assert response.status_code == 201
    assert response.json()["status"] == "trial_started"

    mock_service.start_trial_subscription.assert_awaited_once()


def test_activate_paid(client, mock_service):
    """Активация платной подписки возвращает 200 с данными пользователя."""
    mock_service.activate_paid_subscription = AsyncMock(
        return_value={
            "id": 456,
            "telegram_id": 123,
            "username": "test_user",
            "has_used_trial": False,
            "role": SRoleOut(id=1, name="admin", description=None),
        }
    )

    payload = {"tg_id": 123, "months": 3, "premium": True}

    response = client.post("/api/subscriptions/activate", json=payload)

    assert response.status_code == 200

    mock_service.activate_paid_subscription.assert_awaited_once()


def test_subscription_info(client, mock_service):
    """Возвращает агрегированную информацию о подписке пользователя."""
    mock_service.get_subscription_info = AsyncMock(
        return_value={
            "status": "active",
            "subscription_type": "premium",
            "remaining": "10 days",
            "configs": [],
            "end_date": None,
        }
    )

    response = client.get("/api/subscriptions/info?tg_id=123")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "active"
    assert data["subscription_type"] == "premium"

    mock_service.get_subscription_info.assert_awaited_once()
