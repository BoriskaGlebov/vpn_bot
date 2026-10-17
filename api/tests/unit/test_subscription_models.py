from sqlalchemy.dialects import postgresql

from api.subscription.models import (
    DEVICE_LIMITS,
    SUBSCRIPTION_PRIORITY,
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
