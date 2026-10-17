import datetime

from sqlalchemy.dialects import postgresql

from api.subscription.models import (
    DEVICE_LIMITS,
    SUBSCRIPTION_PRIORITY,
    Subscription,
    SubscriptionType,
)
from api.users.models import User


def test_subscription_priority_covers_every_type():
    """#277: добавление значения в SubscriptionType без приоритета — ошибка теста,
    а не тихий else_=0 в сортировке подписок.
    """
    for sub_type in SubscriptionType:
        assert sub_type in SUBSCRIPTION_PRIORITY, sub_type


def test_device_limits_covers_every_type():
    """#277: то же для лимита устройств — ULTIMATE не должен выпадать в .get(x, 0)."""
    for sub_type in SubscriptionType:
        assert sub_type in DEVICE_LIMITS, sub_type
        assert DEVICE_LIMITS[sub_type] > 0, sub_type


def test_current_subscription_order_by_knows_every_type():
    """Проверка измерением, как в отчёте аудита: компилируем CASE из
    User.subscriptions.order_by и убеждаемся, что каждый тип подписки получил
    собственную ветку, а не упал в ELSE 0.
    """
    order_by = User.__mapper__.relationships["subscriptions"].order_by
    priority_case = order_by[1]
    compiled = str(
        priority_case.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    for sub_type in SubscriptionType:
        assert sub_type.name in compiled, compiled


def test_remaining_days_rounds_up_partial_day():
    """#282: остаток меньше суток у действующей подписки не должен
    показываться как «0 дней» — timedelta.days отбрасывает дробную часть.
    """
    sub = Subscription(
        end_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=12)
    )
    assert sub.remaining_days() == 1


def test_remaining_days_zero_when_already_expired():
    sub = Subscription(
        end_date=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    )
    assert sub.remaining_days() == 0


def test_remaining_days_none_for_unlimited():
    sub = Subscription(end_date=None)
    assert sub.remaining_days() is None


def test_activate_trial_does_not_touch_related_user():
    """#283: правило «пробный период один раз» живёт в сервисе, а не в
    модели — activate() не должен трогать user.has_used_trial и не должен
    требовать self.user вовсе (иначе бросит AttributeError на объекте без
    связанного пользователя, как ниже).
    """
    sub = Subscription()
    sub.activate(days=7, sub_type=SubscriptionType.TRIAL)
    assert sub.type == SubscriptionType.TRIAL
    assert sub.is_active is True
