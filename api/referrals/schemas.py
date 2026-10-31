from pydantic import BaseModel, ConfigDict, Field


class SReferralByInvite(BaseModel):
    """Схема для поиска реферала по ID приглашенного пользователя.

    Используется для передачи фильтров в DAO при поиске записи
    о реферале в базе данных.

    Attributes
        invited_id (int): ID приглашенного пользователя.

    """

    invited_id: int
    model_config = ConfigDict(from_attributes=True)


class RegisterReferralRequest(BaseModel):
    """Запрос на регистрацию реферала.

    Используется для создания связи между пригласителем и приглашённым пользователем.

    Attributes
        invited_user_id (int): Telegram ID приглашённого пользователя.
        inviter_telegram_id (int | None): Telegram ID пригласителя.
            Может быть None, если пользователь пришёл без реферальной ссылки.

    """

    invited_user_id: int = Field(..., description="ID приглашенного пользователя")
    inviter_telegram_id: int | None = Field(
        None, description="Telegram ID пригласителя"
    )


class RegisterReferralResponse(BaseModel):
    """Ответ на регистрацию реферала.

    Attributes
        success (bool): Признак успешности операции.
        message (str): Сообщение с результатом выполнения.

    """

    success: bool
    message: str


class GrantReferralBonusRequest(BaseModel):
    """Запрос на начисление бонуса за реферала.

    Attributes
        invited_user_id (int): Telegram ID приглашённого пользователя.
        months (int): Количество месяцев подписки для начисления.
            Значение должно быть от 1 до 12.

    """

    invited_user_id: int = Field(..., description="ID приглашенного пользователя")
    months: int = Field(1, ge=1, le=12)


class GrantReferralBonusResponse(BaseModel):
    """Ответ на начисление бонуса за реферала.

    Attributes
        success (bool): Признак успешности операции.
        inviter_telegram_id (int | None): Telegram ID пригласителя.
            None, если бонус не был начислен.
        message (str): Сообщение с результатом операции.

    """

    success: bool
    inviter_telegram_id: int | None = None
    message: str
