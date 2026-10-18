import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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
        node_name=None,
        backend=None,
        config_ids=None,
    )


@pytest.mark.asyncio
async def test_handle_expired_subscription(
    scheduler, session, user, expired_subscription, vpn_config
):
    """Истёкшая подписка деактивируется и шлёт пользователю уведомление.

    Удаление конфигов в `_handle_expired` больше не входит (#318) — см.
    тесты `_handle_config_cleanup` ниже.
    """
    user.current_subscription = expired_subscription
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_expired(session, user, expired_subscription)

    assert isinstance(stats, SubscriptionStats)
    assert stats.expired == 1
    assert stats.configs_deleted == 0
    assert vpn_config.status is None

    assert any(isinstance(e, UserNotifyEvent) for e in events)
    assert not any(isinstance(e, DeleteVPNConfigsEvent) for e in events)
    assert not any(isinstance(e, AdminNotifyEvent) for e in events)


@pytest.mark.asyncio
async def test_handle_expired_notifies_about_expired_type_not_other(
    scheduler, session, user, vpn_config
):
    """Уведомление об истечении должно называть тип ИСТЁКШЕЙ подписки, а не
    какой-то другой записи рядом (регрессия): раньше subscription_type брался
    из "другой активной подписки, если есть", и когда другой не было (обычный
    случай — пользователь лишился доступа) подставлялась заглушка "UNKNOWN"
    вместо реального типа (например, PREMIUM).
    """
    premium_sub = SimpleNamespace(
        is_active=True,
        type=SubscriptionType.PREMIUM,
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
        is_expired=lambda: True,
        remaining_days=lambda: -2,
    )
    user.subscriptions = [premium_sub]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_expired(session, user, premium_sub)

    notify_events = [e for e in events if isinstance(e, UserNotifyEvent)]
    assert len(notify_events) == 1
    assert notify_events[0].subscription_type == "PREMIUM"
    assert notify_events[0].active_sbs is False


@pytest.mark.asyncio
async def test_handle_expired_notifies_about_expired_type_with_other_valid(
    scheduler, session, user, active_subscription, vpn_config
):
    """Та же проверка типа в уведомлении, но при наличии другой живой
    подписки — тип в сообщении всё равно должен быть про истёкшую запись,
    не про живую (иначе пользователь увидит "Ваша подписка STANDARD
    истекает через N дней" про подписку, которая вообще не истекает).
    """
    premium_sub = SimpleNamespace(
        is_active=True,
        type=SubscriptionType.PREMIUM,
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
        is_expired=lambda: True,
        remaining_days=lambda: -2,
    )
    user.subscriptions = [premium_sub, active_subscription]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_expired(session, user, premium_sub)

    notify_events = [e for e in events if isinstance(e, UserNotifyEvent)]
    assert len(notify_events) == 1
    assert notify_events[0].subscription_type == "PREMIUM"
    assert notify_events[0].active_sbs is False


@pytest.mark.asyncio
async def test_handle_config_cleanup_deletes_when_no_valid_subscription(
    scheduler, session, user, expired_subscription, vpn_config
):
    """Нет ни одной валидной подписки, прошли сутки — конфиги удаляются."""
    expired_subscription.is_active = False
    user.subscriptions = [expired_subscription]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_config_cleanup(session, user)

    assert stats.configs_deleted == 1
    assert vpn_config.status == VPNConfigStatus.PENDING_DELETE
    assert any(isinstance(e, DeleteVPNConfigsEvent) for e in events)
    assert any(isinstance(e, AdminNotifyEvent) for e in events)


@pytest.mark.asyncio
async def test_handle_config_cleanup_keeps_configs_with_other_valid_subscription(
    scheduler, session, user, active_subscription, expired_subscription, vpn_config
):
    """Рядом есть живая неистёкшая подписка (#299) — конфиги не трогаем."""
    expired_subscription.is_active = False
    user.subscriptions = [expired_subscription, active_subscription]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_config_cleanup(session, user)

    assert stats.configs_deleted == 0
    assert vpn_config.status is None
    assert events == []


@pytest.mark.asyncio
async def test_handle_config_cleanup_waits_a_day_after_last_expiry(
    scheduler, session, user, vpn_config
):
    """Истекла меньше суток назад — удаление откладывается (#299)."""
    recently_expired = SimpleNamespace(
        is_active=False,
        type=SubscriptionType.STANDARD,
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=5),
        is_expired=lambda: True,
        remaining_days=lambda: 0,
    )
    user.subscriptions = [recently_expired]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._handle_config_cleanup(session, user)

    assert stats.configs_deleted == 0
    assert events == []


@pytest.mark.asyncio
async def test_handle_expiring_soon(scheduler, user, active_subscription):
    """Подписка истекает через 2 дня -> шлётся ровно одно предупреждающее уведомление."""
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
    """Превышен лимит устройств -> лишние конфиги удаляются по FIFO."""
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
            node_name=None,
            backend=None,
            config_ids=None,
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
    """У пользователя нет подписки -> обработка не даёт ни статистики, ни событий."""
    user.current_subscription = None

    stats, events = await scheduler._process_user(session, user)

    assert stats.expired == 0
    assert stats.configs_deleted == 0
    assert events == []


@pytest.mark.asyncio
async def test_process_user_deactivates_abandoned_active_subscription(
    scheduler, session, user, expired_subscription
):
    """#275: current_subscription выбирает только приоритетную запись — если
    у пользователя осталась ещё одна истёкшая активная подписка (брошенная
    от старой покупки/триала), планировщик должен деактивировать и её, а не
    только приоритетную.
    """
    priority_sub = expired_subscription  # уже истекла, is_active=True
    abandoned_sub = SimpleNamespace(
        is_active=True,
        type=SimpleNamespace(value="trial"),
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5),
        is_expired=lambda: True,
        remaining_days=lambda: -5,
    )

    user.current_subscription = priority_sub
    user.subscriptions = [priority_sub, abandoned_sub]
    user.vpn_configs = []

    stats, events = await scheduler._process_user(session, user)

    assert priority_sub.is_active is False
    assert abandoned_sub.is_active is False
    assert stats.expired == 2


@pytest.mark.asyncio
async def test_process_user_keeps_configs_when_other_subscription_still_valid(
    scheduler, session, user, active_subscription, vpn_config
):
    """#299: живая оплаченная подписка + брошенная истёкшая запись рядом —
    планировщик не должен удалять конфиги платящего пользователя.

    Регрессия на правку #275: тот фикс научил планировщик обходить ВСЕ
    активные подписки и деактивировать брошенные, но `_handle_expired` для
    брошенной записи удалял `user.vpn_configs` целиком, не проверяя, что у
    пользователя рядом есть другая активная неистёкшая подписка.
    """
    abandoned_sub = SimpleNamespace(
        is_active=True,
        type=SimpleNamespace(value="trial"),
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10),
        is_expired=lambda: True,
        remaining_days=lambda: -10,
    )

    user.current_subscription = active_subscription
    user.subscriptions = [active_subscription, abandoned_sub]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._process_user(session, user)

    assert abandoned_sub.is_active is False
    assert stats.configs_deleted == 0
    assert vpn_config.status is None
    assert not any(isinstance(e, DeleteVPNConfigsEvent) for e in events)


@pytest.mark.asyncio
async def test_process_user_deletes_configs_once_for_two_expired_subscriptions(
    scheduler, session, user, vpn_config
):
    """#318: у пользователя две истёкшие подписки (приоритетная + брошенная) —
    конфиги должны уйти на удаление ровно один раз за прогон, а не дважды.

    Регрессия на правку #299: `_handle_expired` вызывается для каждой
    истёкшей записи, и раньше конфиги помечались на удаление в каждом
    вызове — удвоенные уведомления и статистика на тех же двух конфигах.
    """
    priority_sub = SimpleNamespace(
        is_active=True,
        type=SubscriptionType.PREMIUM,
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10),
        is_expired=lambda: True,
        remaining_days=lambda: -10,
    )
    abandoned_sub = SimpleNamespace(
        is_active=True,
        type=SimpleNamespace(value="trial"),
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30),
        is_expired=lambda: True,
        remaining_days=lambda: -30,
    )

    user.current_subscription = priority_sub
    user.subscriptions = [priority_sub, abandoned_sub]
    user.vpn_configs = [vpn_config]

    stats, events = await scheduler._process_user(session, user)

    assert priority_sub.is_active is False
    assert abandoned_sub.is_active is False
    assert stats.configs_deleted == 1
    assert len([e for e in events if isinstance(e, DeleteVPNConfigsEvent)]) == 1
    assert len([e for e in events if isinstance(e, AdminNotifyEvent)]) == 1


@pytest.mark.asyncio
async def test_check_all_subscriptions(scheduler, session, user, expired_subscription):
    """Сквозной прогон по всем пользователям: агрегирует статистику.

    Коммит сессии — забота внешней границы транзакции (`get_session()`),
    сервис его больше не вызывает сам (см. api/scheduler/services.py).
    """
    user.current_subscription = expired_subscription
    user.subscriptions = [expired_subscription]
    user.vpn_configs = []

    # Мокаем результат SQLAlchemy
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [user]
    session.execute = AsyncMock(return_value=result_mock)

    stats, events = await scheduler.check_all_subscriptions(session)

    assert stats.checked == 1
    assert stats.expired == 1
    session.commit.assert_not_awaited()
    assert isinstance(events, list)
