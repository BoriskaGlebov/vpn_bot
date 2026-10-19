from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SUserTelegramID(BaseModel):
    """Схема для идентификации пользователя по Telegram ID."""

    telegram_id: int = Field(
        ..., description="Уникальный идентификатор пользователя в Telegram"
    )

    model_config = ConfigDict(from_attributes=True)


class SUser(SUserTelegramID):
    """Схема пользователя Telegram с расширенной информацией."""

    username: str | None = Field(None, description="Имя пользователя в Telegram")
    first_name: str | None = Field(None, description="Имя пользователя")
    last_name: str | None = Field(None, description="Фамилия пользователя")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class SUsernameUpdate(BaseModel):
    """Схема обновления username при повторном входе пользователя.

    Telegram-username изменяем и необязателен — хранимое значение иначе
    тихо устаревает по сравнению с актуальным (см. #242).

    Attributes
        username (str | None): Текущее значение username из Telegram.

    """

    username: str | None = Field(
        None, description="Текущее имя пользователя в Telegram"
    )

    model_config = ConfigDict(from_attributes=True)


class SRole(BaseModel):
    """Схема роли пользователя."""

    name: str = Field(..., description="Уникальное имя роли")
    description: str | None = Field(default=None, description="Описание роли")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class SSubscription(BaseModel):
    """Схема для создания подписки."""

    user_id: int = Field(..., description="Идентификатор пользователя")
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class SRoleOut(BaseModel):
    """Схема для вывода роли пользователя."""

    id: int = Field(..., description="Уникальный идентификатор роли")
    name: str = Field(..., description="Имя роли")
    description: str | None = Field(None, description="Описание роли")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    def __str__(self) -> str:
        """Строковое представление роли."""
        return f"{self.name} - {self.description}"


class SSubscriptionOut(BaseModel):
    """Схема для вывода информации о подписке пользователя."""

    id: int = Field(..., description="ID подписки")
    type: str | None = Field(
        None, description="Тип подписки (standart/premium/trial и т.д.)"
    )
    is_active: bool = Field(..., description="Статус активности подписки")
    end_date: datetime | None = Field(
        None, description="Дата окончания подписки (может отсутствовать)"
    )
    created_at: datetime = Field(..., description="Дата создания подписки")

    model_config = ConfigDict(from_attributes=True)

    def __str__(self) -> str:
        """Строковое представление подписки."""
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
    node_name: str | None = Field(None, description="Имя ноды/локации")
    backend: str | None = Field(None, description='Бэкенд ("amnezia" | "xray")')
    protocol: str | None = Field(None, description="Протокол/версия внутри бэкенда")
    config_ids: list[str] | None = Field(
        None, description="Для XRay — uuid клиентов на панели"
    )
    created_at: datetime = Field(..., description="Дата и время создания конфига")

    model_config = ConfigDict(from_attributes=True)


class SUserOut(BaseModel):
    """Полная схема пользователя с ролями, подпиской и VPN."""

    id: int = Field(..., description="ID пользователя в БД")
    telegram_id: int = Field(..., description="Telegram ID пользователя")
    # Telegram-username необязателен, изменяем и переиспользуем — не может
    # быть обязательным непустым полем (см. #242).
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
    current_subscription: SSubscriptionOut | None = Field(
        None, description="Текущая подписка пользователя"
    )

    model_config = ConfigDict(from_attributes=True)


class SUserWithReferralStats(SUserOut):
    """Расширенная схема пользователя с реферальной статистикой."""

    referrals_count: int = Field(
        ...,
        description="Сколько пользователей пригласил",
        examples=[10],
    )

    paid_referrals_count: int = Field(
        ...,
        description="Сколько приглашённых оплатили подписку",
        examples=[4],
    )

    referral_conversion: float = Field(
        ...,
        description="Конверсия рефералов (paid / total)",
        examples=[0.4],
    )

    model_config = ConfigDict(from_attributes=True)
