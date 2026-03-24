from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.subscription.enums import TrialStatus
from shared.enums.admin_enum import RoleEnum


class SSubscriptionCheck(BaseModel):
    """Результат проверки подписки пользователя.

    Attributes
        premium: True, если у пользователя активна премиум-подписка.
        role: Роль пользователя в системе.
        is_active: True, если текущая подписка активна.

    """

    premium: bool = Field(..., description="Активна ли премиум-подписка")
    role: RoleEnum = Field(..., description="Роль пользователя")
    is_active: bool = Field(..., description="Активность текущей подписки")


class STrialActivate(BaseModel):
    """Запрос на активацию пробного периода подписки.

    Attributes
        tg_id: Telegram ID пользователя.
        days: Количество дней пробного периода (> 0).

    """

    tg_id: int = Field(..., description="Telegram ID пользователя")
    days: int = Field(..., gt=0, description="Количество дней пробного периода")


class STrialActivateResponse(BaseModel):
    """Ответ на активацию пробного периода.

    Attributes
        status: Статус активации trial.

    """

    status: TrialStatus


class ActivateSubscriptionRequest(BaseModel):
    """Запрос на активацию платной подписки.

    Attributes
        tg_id: Telegram ID пользователя.
        months: Количество месяцев подписки (1–24).
        premium: True → премиум подписка, False → стандартная.

    """

    tg_id: int = Field(..., description="Telegram ID пользователя")
    months: int = Field(..., ge=1, le=24, description="Количество месяцев")
    premium: bool = Field(..., description="Флаг премиум подписки")


class SSubscription(BaseModel):
    """Схема подписки пользователя.

    Attributes
        user_id (int): Идентификатор пользователя, которому принадлежит подписка.

    """

    user_id: int = Field(..., description="User ID")
    model_config = ConfigDict(from_attributes=True)


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
