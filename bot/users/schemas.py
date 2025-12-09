from datetime import datetime

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

    model_config = ConfigDict(from_attributes=True)


class SRole(BaseModel):
    """Схема роли пользователя.

    Attributes
        name (str): Уникальное имя роли.
        description (Optional[str]): Описание роли.

    """

    name: str = Field(..., description="Уникальное имя роли")
    description: str | None = Field(None, description="Описание роли")

    model_config = ConfigDict(from_attributes=True)


class SSubscription(BaseModel):
    """Схема для создания подписки.

    Attributes
        user_id (int): Идентификатор подписки, используется в момент создания.

    """

    user_id: int = Field(..., description="Идентификатор пользователя")
    model_config = ConfigDict(from_attributes=True)


class SRoleOut(BaseModel):
    """Схема для вывода роли пользователя."""

    id: int = Field(..., description="Уникальный идентификатор роли")
    name: str = Field(..., description="Имя роли")
    description: str | None = Field(None, description="Описание роли")

    model_config = ConfigDict(from_attributes=True)

    def __str__(self) -> str:
        """Строковое представление как в модели SRole."""
        return f"{self.name} - {self.description}"


class SSubscriptionOut(BaseModel):
    """Схема для вывода информации о подписке пользователя."""

    id: int = Field(..., description="ID подписки")
    type: str | None = Field(
        None, description="Тип подписки (free/premium/trial и т.д.)"
    )
    is_active: bool = Field(..., description="Статус активности подписки")
    end_date: datetime | None = Field(
        None, description="Дата окончания подписки (может отсутствовать)"
    )
    created_at: datetime = Field(..., description="Дата создания подписки")

    model_config = ConfigDict(from_attributes=True)

    def __str__(self) -> str:
        """Строковое представление как в модели Subscription."""
        status = "Активна" if self.is_active else "Неактивна"
        stat_type = self.type.upper() if self.type else "NO_STATUS"
        until = (
            self.end_date.strftime("%Y-%m-%d %H:%M") if self.end_date else "бессрочная"
        )
        return f"{status} {stat_type} (до {until})"


class SVPNConfigOut(BaseModel):
    """Схема для вывода VPN конфигов пользователя."""

    id: int = Field(..., description="ID конфига")
    file_name: str = Field(..., description="Имя файла/конфига")
    pub_key: str = Field(..., description="Публичный ключ")

    model_config = ConfigDict(from_attributes=True)


class SUserOut(BaseModel):
    """Полная схема пользователя с ролями, подпиской и VPN."""

    id: int = Field(..., description="ID пользователя в БД")
    telegram_id: int = Field(..., description="Telegram ID пользователя")
    username: str | None = Field(None, description="Username в Telegram")
    first_name: str | None = Field(None, description="Имя пользователя")
    last_name: str | None = Field(None, description="Фамилия пользователя")
    has_used_trial: bool = Field(..., description="Использовал ли пользователь триал")

    role: SRoleOut = Field(..., description="Роль пользователя")
    subscriptions: list[SSubscriptionOut] = Field(
        default_factory=list, description="Список подписок пользователя"
    )
    vpn_configs: list[SVPNConfigOut] = Field(
        default_factory=list,
        description="Список VPN конфигураций пользователя",
    )

    model_config = ConfigDict(from_attributes=True)
