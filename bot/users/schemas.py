from pydantic import BaseModel, ConfigDict, Field


class SUserTelegramID(BaseModel):
    """Схема для идентификации пользователя по Telegram ID.

    Attributes
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.

    """

    telegram_id: int = Field(
        ..., description="Уникальный идентификатор пользователя в Telegram"
    )

    model_config = ConfigDict(from_attributes=True)


class SUser(SUserTelegramID):
    """Схема пользователя Telegram с расширенной информацией.

    Attributes
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.
        username (Optional[str]): Имя пользователя в Telegram.
        first_name (Optional[str]): Имя пользователя.
        last_name (Optional[str]): Фамилия пользователя.

    """

    username: str | None = Field(None, description="Имя пользователя в Telegram")
    first_name: str | None = Field(None, description="Имя пользователя")
    last_name: str | None = Field(None, description="Фамилия пользователя")


class SRole(BaseModel):
    """Схема роли пользователя."""

    name: str = Field(..., description="Уникальное имя роли")
    description: str | None = Field(None, description="Описание роли")

    model_config = ConfigDict(from_attributes=True)


class SSubscription(BaseModel):
    """Схема для создания подписки."""

    user_id: int = Field(..., description="Идентификатор пользователя")
    model_config = ConfigDict(from_attributes=True)
