from pydantic import BaseModel

from api.scheduler.enums import SubscriptionEventType


class EventBase(BaseModel):
    """Базовый класс события подписочной системы.

    Attributes
        type: Тип события.

    """

    type: SubscriptionEventType
    user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class UserNotifyEventSchema(EventBase):
    """Событие уведомления пользователя.

    Attributes
        message: текст уведомления
         subscription_type: Тип подписки
         remaining_days: Осталось дней
         active_sbs: Активна ли подписка

    """

    message: str
    subscription_type: str
    remaining_days: int
    active_sbs: bool


class DeletedVPNConfigSchema(BaseModel):
    """Схема данных для удалённого VPN-конфига.

    Используется для сериализации информации о конфигурации VPN, которая была удалена.
    Содержит минимальные данные для идентификации и дальнейшей обработки события.

    Attributes
        file_name (str): Имя файла конфигурации VPN.
        pub_key (str): Публичный ключ VPN-конфига.

    """

    file_name: str
    pub_key: str


class DeleteVPNConfigsEventSchema(EventBase):
    """Событие удаления VPN конфигураций пользователя.

    Attributes
        configs: список удаляемых конфигураций

    """

    configs: list[DeletedVPNConfigSchema]


class DeleteProxyEventSchema(EventBase):
    """Событие удаления proxy пользователя."""

    pass


class AdminNotifyEventSchema(EventBase):
    """Событие уведомления администратора.

    Attributes
        message: текст уведомления

    """

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
        configs_deleted: Количество удалённых конфигураций.

    """

    checked: int
    expired: int
    configs_deleted: int


class CheckAllSubscriptionsResponse(BaseModel):
    """Ответ массовой проверки подписок.

    Attributes
        stats: агрегированная статистика обработки
        events: список событий, сгенерированных системой

    """

    stats: SubscriptionStatsSchema
    events: list[
        UserNotifyEventSchema
        | DeleteVPNConfigsEventSchema
        | DeleteProxyEventSchema
        | AdminNotifyEventSchema
    ]
