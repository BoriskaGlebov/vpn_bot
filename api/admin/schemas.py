from pydantic import BaseModel, Field

from shared.enums.admin_enum import RoleEnum


class SChangeRole(BaseModel):
    """Схема запроса на изменение роли пользователя."""

    telegram_id: int = Field(
        ...,
        description="Уникальный Telegram ID пользователя",
    )
    role_name: RoleEnum = Field(
        ...,
        description="Новая роль пользователя (user, admin, founder)",
    )


class SExtendSubscription(BaseModel):
    """Схема запроса на продление подписки пользователя."""

    telegram_id: int = Field(
        ...,
        description="Уникальный Telegram ID пользователя",
    )
    months: int = Field(
        ...,
        ge=1,
        description="Количество месяцев для продления подписки (>= 1)",
    )
