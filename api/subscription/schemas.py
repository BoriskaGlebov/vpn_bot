from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.enums.admin_enum import RoleEnum


class SSubscriptionCheck(BaseModel):
    """Ответ проверки подписки пользователя."""

    premium: bool = Field(..., description="Есть ли премиум-подписка")
    role: RoleEnum = Field(..., description="Роль пользователя (user, admin, founder)")
    is_active: bool = Field(..., description="Активна ли текущая подписка")

class STrialActivate(BaseModel):
    """Запрос на активацию пробного периода."""

    tg_id: int = Field(..., description="Telegram ID пользователя")
    days: int = Field(..., gt=0, description="Количество дней пробного периода")


class TrialStatus(str, Enum):
    STARTED = "trial_started"


class STrialActivateResponse(BaseModel):
    status: TrialStatus

class ActivateSubscriptionRequest(BaseModel):
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
    type: str


class UserNotifyEventSchema(EventBase):
    type: Literal["user_notify"]
    user_id: int
    message: str


class DeleteVPNConfigsEventSchema(EventBase):
    type: Literal["delete_vpn_configs"]
    user_id: int
    configs: List[str]


class DeleteProxyEventSchema(EventBase):
    type: Literal["delete_proxy"]
    user_id: int


class AdminNotifyEventSchema(EventBase):
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
    checked: int
    expired: int
    notified: int
    configs_deleted: int

class CheckAllSubscriptionsResponse(BaseModel):
    stats: SubscriptionStatsSchema
    events: list[SubscriptionEventSchema]