from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.main import app
from api.scheduler.dependencies import get_subscription_scheduler_service
from api.scheduler.domain.event import UserNotifyEvent
from api.scheduler.domain.stats import SubscriptionStats
from api.scheduler.enums import SubscriptionEventType
from api.tests.conftest import fake_admin


@pytest.fixture
def mock_scheduler_service():
    return AsyncMock()


@pytest.fixture
def client(make_client, mock_scheduler_service):
    """TestClient с переопределёнными зависимостями роутера планировщика."""
    with make_client(
        {
            get_subscription_scheduler_service: lambda: mock_scheduler_service,
            get_session: lambda: AsyncMock(),
            check_admin_role: fake_admin,
        }
    ) as c:
        yield c


def test_check_all_subscriptions_success(client, mock_scheduler_service):
    """Полная проверка подписок: статистика и события корректно сериализуются."""
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
    """Проверка без затронутых подписок -> пустой список событий."""
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


def fake_non_admin():
    """Имитирует check_admin_role для не-администратора (403)."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def test_check_all_subscriptions_forbidden(client, mock_scheduler_service):
    """Пользователь без прав администратора получает 403."""
    app.dependency_overrides[check_admin_role] = fake_non_admin

    response = client.post("/scheduler/check-all")

    assert response.status_code == 403
