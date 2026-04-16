# tests/api/test_scheduler_router.py
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.main import app
from api.scheduler.dependencies import get_subscription_scheduler_service
from api.scheduler.domain.event import UserNotifyEvent
from api.scheduler.domain.stats import SubscriptionStats
from api.scheduler.enums import SubscriptionEventType
from shared.enums.admin_enum import RoleEnum


def fake_admin():
    return SimpleNamespace(
        id=1,
        telegram_id=123,
        role=SimpleNamespace(name=RoleEnum.ADMIN.value),
    )


@pytest.fixture
def mock_scheduler_service():
    service = AsyncMock()
    return service


@pytest.fixture
def client(mock_scheduler_service):
    with patch("api.main.init_default_roles_admins", new=AsyncMock()):
        app.dependency_overrides.clear()

        app.dependency_overrides[get_subscription_scheduler_service] = (
            lambda: mock_scheduler_service
        )
        app.dependency_overrides[get_session] = lambda: AsyncMock()
        app.dependency_overrides[check_admin_role] = fake_admin

        with TestClient(app) as test_client:
            yield test_client

        app.dependency_overrides.clear()


def test_check_all_subscriptions_success(client, mock_scheduler_service):
    # Подготовка статистики
    stats = SubscriptionStats()
    stats.checked = 1
    stats.expired = 1
    stats.notified = 1
    stats.configs_deleted = 2

    # Подготовка события
    event = UserNotifyEvent(
        type=SubscriptionEventType.USER_NOTIFY,
        user_id=123,
        username="test",
        first_name="Test",
        last_name="User",
        message="Подписка истекла",
        subscription_type="STANDARD",
        remaining_days=0,
        active_sbs=False,
    )

    # Мокаем ответ сервиса
    mock_scheduler_service.check_all_subscriptions.return_value = (
        stats,
        [event],
    )

    # Выполнение запроса
    response = client.post("/scheduler/check-all")

    # Проверки HTTP-ответа
    assert response.status_code == 200
    data = response.json()

    # Проверка статистики
    assert data["stats"]["checked"] == 1
    assert data["stats"]["expired"] == 1
    assert data["stats"]["configs_deleted"] == 2

    # Проверка событий
    assert len(data["events"]) == 1
    assert data["events"][0]["type"] == SubscriptionEventType.USER_NOTIFY.value
    assert data["events"][0]["user_id"] == 123

    # Проверка вызова сервиса
    mock_scheduler_service.check_all_subscriptions.assert_awaited_once()


def test_check_all_subscriptions_no_events(client, mock_scheduler_service):
    stats = SubscriptionStats()
    stats.checked = 0

    mock_scheduler_service.check_all_subscriptions.return_value = (
        stats,
        [],
    )

    response = client.post("/scheduler/check-all")

    assert response.status_code == 200
    data = response.json()

    assert data["stats"]["checked"] == 0
    assert data["events"] == []


from fastapi import HTTPException, status


def fake_non_admin():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def test_check_all_subscriptions_forbidden(client, mock_scheduler_service):
    from api.admin.dependencies import check_admin_role
    from api.main import app

    app.dependency_overrides[check_admin_role] = fake_non_admin

    response = client.post("/scheduler/check-all")

    assert response.status_code == 403
