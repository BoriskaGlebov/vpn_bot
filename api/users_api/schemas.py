from datetime import datetime

from pydantic import BaseModel, ConfigDict

from bot.subscription.models import SubscriptionType


class SubscriptionRead(BaseModel):
    """Схема подписки пользователя."""

    id: int
    type: SubscriptionType | None = None
    is_active: bool
    start_date: datetime
    end_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SRoleRead(BaseModel):
    """Схема роли пользователя (для вложенной выдачи)."""

    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SUserBase(BaseModel):
    """Базовая схема пользователя без связанных данных."""

    id: int
    telegram_id: int
    username: str
    first_name: str | None = None
    last_name: str | None = None
    has_used_trial: bool
    vpn_files_count: int

    model_config = ConfigDict(from_attributes=True)


class SUserRead(SUserBase):
    """Расширенная схема пользователя с ролями и подписками."""

    role: SRoleRead | None = None
    current_subscription: SubscriptionRead | None = None
    subscriptions: list[SubscriptionRead] | None = []

    model_config = ConfigDict(from_attributes=True)
