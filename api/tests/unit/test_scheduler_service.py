import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from users.schemas import SVPNConfigOut

from api.scheduler.domain.event import (
    AdminNotifyEvent,
    DeleteVPNConfigsEvent,
    UserNotifyEvent,
)
from api.scheduler.domain.stats import SubscriptionStats
from api.scheduler.enums import SubscriptionEventType
from api.scheduler.services import SubscriptionScheduler
from api.subscription.models import DEVICE_LIMITS, Subscription, SubscriptionType
from api.users.models import User
from api.vpn.models import VPNConfigStatus
from shared.enums.admin_enum import RoleEnum

# -----------------------
# Общие фикстуры
# -----------------------


@pytest.fixture
def scheduler() -> SubscriptionScheduler:
    return SubscriptionScheduler()


@pytest.fixture
def session():
    """Мок асинхронной сессии SQLAlchemy."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def user():
    user = MagicMock(spec=User)
    user.id = 1
    user.telegram_id = 123
    user.role.name = RoleEnum.USER
    user.has_used_trial = False

    sub = MagicMock(spec=Subscription)
    sub.is_active = True
    sub.type = SubscriptionType.STANDARD
    sub.extend = MagicMock()

    user.current_subscription = sub
    user.subscriptions = [sub]
    user.vpn_configs = []
    return user


@pytest.fixture
def active_subscription():
    """Активная подписка."""
    return SimpleNamespace(
        is_active=True,
        type=SubscriptionType.STANDARD,
        end_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=5),
        is_expired=lambda: False,
        remaining_days=lambda: 5,
    )


@pytest.fixture
def expired_subscription():
    """Истёкшая подписка более суток назад."""
    return SimpleNamespace(
        is_active=True,
        type=SimpleNamespace(value="basic"),
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
        is_expired=lambda: True,
        remaining_days=lambda: -2,
    )


@pytest.fixture
def vpn_config():
    """VPN-конфигурация."""
    return SimpleNamespace(
        file_name="config1.conf",
        pub_key="pubkey123",
        created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10),
        status=None,
    )


@pytest.mark.asyncio
async def test_handle_expired_subscription(
    scheduler, session, user, expired_subscription, vpn_config
):
    user.current_subscription = expired_subscription
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_expired(session, user, expired_subscription)

    # Проверка статистики
    assert isinstance(stats, SubscriptionStats)
    assert stats.expired == 1
    assert stats.configs_deleted == 1

    # Проверка изменения статуса конфигурации
    assert vpn_config.status == VPNConfigStatus.PENDING_DELETE

    # Проверка типов событий
    assert any(isinstance(e, UserNotifyEvent) for e in events)
    assert any(isinstance(e, DeleteVPNConfigsEvent) for e in events)
    assert any(isinstance(e, AdminNotifyEvent) for e in events)


@pytest.mark.asyncio
async def test_handle_expiring_soon(scheduler, user, active_subscription):
    active_subscription.remaining_days = lambda: 2
    user.current_subscription = active_subscription

    stats, events = await scheduler._handle_expiring_soon(user, active_subscription)

    assert stats.expired == 0
    assert len(events) == 1
    assert isinstance(events[0], UserNotifyEvent)
    assert events[0].type == SubscriptionEventType.USER_NOTIFY


@pytest.mark.asyncio
async def test_handle_active_limit_exceeded(
    scheduler, session, user, active_subscription
):
    user.current_subscription = active_subscription

    # Устанавливаем лимит
    DEVICE_LIMITS[active_subscription.type] = 1

    # Создаём 3 конфигурации
    now = datetime.datetime.now(datetime.UTC)
    user.vpn_configs = [
        SimpleNamespace(
            file_name=f"config{i}.conf",
            pub_key=f"key{i}",
            created_at=now - datetime.timedelta(days=i),
            status=None,
        )
        for i in range(3)
    ]

    stats, events = await scheduler._handle_active_limit_exceeded(session, user)

    # Должно быть удалено 2 конфига (FIFO)
    assert stats.configs_deleted == 2

    delete_events = [e for e in events if isinstance(e, DeleteVPNConfigsEvent)]
    admin_events = [e for e in events if isinstance(e, AdminNotifyEvent)]

    assert len(delete_events) == 1
    assert len(admin_events) == 2


@pytest.mark.asyncio
async def test_process_user_without_subscription(scheduler, session, user):
    user.current_subscription = None

    stats, events = await scheduler._process_user(session, user)

    assert stats.expired == 0
    assert stats.configs_deleted == 0
    assert events == []


@pytest.mark.asyncio
async def test_check_all_subscriptions(scheduler, session, user, expired_subscription):
    user.current_subscription = expired_subscription
    user.vpn_configs = []

    # Мокаем результат SQLAlchemy
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [user]
    session.execute = AsyncMock(return_value=result_mock)

    stats, events = await scheduler.check_all_subscriptions(session)

    assert stats.checked == 1
    assert stats.expired == 1
    session.commit.assert_awaited_once()
    assert isinstance(events, list)
