from api.scheduler.domain.event import (
    AdminNotifyEvent,
    DeleteProxyEvent,
    DeleteVPNConfigsEvent,
    SubscriptionEvent,
    UserNotifyEvent,
)
from api.scheduler.domain.stats import SubscriptionStats
from shared.schemas.scheduler import (
    AdminNotifyEventSchema,
    DeleteProxyEventSchema,
    DeleteVPNConfigsEventSchema,
    SubscriptionEventSchema,
    SubscriptionStatsSchema,
    UserNotifyEventSchema,
)


def map_event(event: SubscriptionEvent) -> SubscriptionEventSchema:
    """Преобразует объект доменной модели события в Pydantic-схему.

    Используется для сериализации событий подписок перед отправкой в API
    или логикой, которая работает с Pydantic-моделями.

    Args:
        event (SubscriptionEvent): Экземпляр события доменной модели.

    Returns
        SubscriptionEventSchema: Соответствующая Pydantic-схема события.

    Raises
        ValueError: Если тип события неизвестен и нет соответствующей схемы.

    """
    if isinstance(event, UserNotifyEvent):
        return UserNotifyEventSchema(**event.__dict__)

    if isinstance(event, AdminNotifyEvent):
        return AdminNotifyEventSchema(**event.__dict__)

    if isinstance(event, DeleteProxyEvent):
        return DeleteProxyEventSchema(**event.__dict__)

    if isinstance(event, DeleteVPNConfigsEvent):
        return DeleteVPNConfigsEventSchema(**event.__dict__)

    raise ValueError(f"Неизвестный event type: {type(event)}")


def map_stats(stats: SubscriptionStats) -> SubscriptionStatsSchema:
    """Преобразует объект статистики подписок в Pydantic-схему.

    Используется для сериализации агрегированной статистики подписок
    перед отправкой через API.

    Args:
        stats (SubscriptionStats): Экземпляр доменной модели статистики.

    Returns
        SubscriptionStatsSchema: Соответствующая Pydantic-схема статистики.

    """
    return SubscriptionStatsSchema(**stats.__dict__)
