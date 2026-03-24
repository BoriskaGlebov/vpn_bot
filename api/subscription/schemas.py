from typing import Literal

from pydantic import BaseModel


class EventBase(BaseModel):
    """Базовый класс события подписочной системы.

    Attributes
        type: Тип события.

    """

    type: str


class UserNotifyEventSchema(EventBase):
    """Событие уведомления пользователя.

    Attributes
        type: фиксированный тип события user_notify
        user_id: ID пользователя
        message: текст уведомления

    """

    type: Literal["user_notify"]
    user_id: int
    message: str


class DeleteVPNConfigsEventSchema(EventBase):
    """Событие удаления VPN конфигураций пользователя.

    Attributes
        type: фиксированный тип delete_vpn_configs
        user_id: ID пользователя
        configs: список удаляемых конфигураций

    """

    type: Literal["delete_vpn_configs"]
    user_id: int
    configs: list[str]


class DeleteProxyEventSchema(EventBase):
    """Событие удаления proxy пользователя.

    Attributes
        type: фиксированный тип delete_proxy
        user_id: ID пользователя

    """

    type: Literal["delete_proxy"]
    user_id: int


class AdminNotifyEventSchema(EventBase):
    """Событие уведомления администратора.

    Attributes
        type: фиксированный тип admin_notify
        user_id: ID пользователя
        message: текст уведомления

    """

    type: Literal["admin_notify"]
    user_id: int
    message: str


SubscriptionEventSchema = (
    UserNotifyEventSchema
    | DeleteVPNConfigsEventSchema
    | DeleteProxyEventSchema
    | AdminNotifyEventSchema
)


class SubscriptionStatsSchema(BaseModel):
    """Статистика обработки подписок.

    Attributes
        checked: Количество проверенных подписок.
        expired: Количество истёкших подписок.
        notified: Количество отправленных уведомлений.
        configs_deleted: Количество удалённых конфигураций.

    """

    checked: int
    expired: int
    notified: int
    configs_deleted: int


class CheckAllSubscriptionsResponse(BaseModel):
    """Ответ массовой проверки подписок.

    Attributes
        stats: агрегированная статистика обработки
        events: список событий, сгенерированных системой

    """

    stats: SubscriptionStatsSchema
    events: list[SubscriptionEventSchema]
