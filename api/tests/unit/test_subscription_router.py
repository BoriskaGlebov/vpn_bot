from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_current_user, get_session
from api.main import app
from api.subscription.dependencies import get_subscription_service
from api.subscription.router import router
from api.subscription.schemas import SSubscriptionCheck, SSubscriptionInfo
from api.subscription.services import SubscriptionService
from api.users.schemas import SRoleOut
from shared.enums.admin_enum import RoleEnum


def fake_admin():
    return SimpleNamespace(
        id=1,
        telegram_id=123,
        role=SimpleNamespace(name=RoleEnum.ADMIN.value),
    )


def fake_user():
    return SimpleNamespace(
        id=1,
        telegram_id=123,
        username="test",
        has_used_trial=False,
        role=SimpleNamespace(name=RoleEnum.ADMIN.value),
    )


@pytest.fixture
def mock_service():
    return MagicMock(spec=SubscriptionService)


@pytest.fixture
def client(mock_service):
    with patch(
        "api.main.init_default_roles_admins",
        new=AsyncMock(),
    ):
        app.dependency_overrides = {}
        app.middleware_stack = None
        app.dependency_overrides[get_subscription_service] = lambda: mock_service
        app.dependency_overrides[get_session] = lambda: AsyncMock()
        app.dependency_overrides[get_current_user] = fake_user
        app.dependency_overrides[check_admin_role] = fake_admin

        return TestClient(app)
    app.dependency_overrides.clear()


def test_check_premium(client, mock_service):
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
    mock_service.start_trial_subscription = AsyncMock(return_value=None)

    payload = {"tg_id": 123, "days": 10}

    response = client.post("/api/subscriptions/trial/activate", json=payload)

    assert response.status_code == 201
    assert response.json()["status"] == "trial_started"

    mock_service.start_trial_subscription.assert_awaited_once()


def test_activate_paid(client, mock_service):
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
