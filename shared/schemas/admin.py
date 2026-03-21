from pydantic import BaseModel, Field

from shared.enums.admin_enum import RoleEnum


class SChangeRole(BaseModel):
    """Схема запроса на изменение роли пользователя.

    Используется для административного изменения роли пользователя
    в системе (например: user → admin, user → founder).

    Attributes
        telegram_id (int): Уникальный Telegram ID пользователя.
        role_name (RoleEnum): Новая роль пользователя.

    """

    telegram_id: int = Field(
        ...,
        description="Уникальный Telegram ID пользователя",
    )
    role_name: RoleEnum = Field(
        ...,
        description="Новая роль пользователя (user, admin, founder)",
    )


class SExtendSubscription(BaseModel):
    """Схема запроса на продление подписки пользователя.

    Используется для увеличения срока активной подписки пользователя
    на указанное количество месяцев.

    Attributes
        telegram_id (int): Уникальный Telegram ID пользователя.
        months (int): Количество месяцев для продления подписки.

    """

    telegram_id: int = Field(
        ...,
        description="Уникальный Telegram ID пользователя",
    )
    months: int = Field(
        ...,
        ge=1,
        description="Количество месяцев для продления подписки (>= 1)",
    )
