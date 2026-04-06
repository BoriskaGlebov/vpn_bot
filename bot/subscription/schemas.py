from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import TrialStatus


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
    used_trial: bool = Field(..., description="Использован ли триал.")


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


class SVPNConfig(BaseModel):
    """Схема информации о VPN-конфиге.

    Attributes
        file_name (str): Имя файла конфигурации.

    """

    file_name: str


class SSubscriptionInfo(BaseModel):
    """Схема информации о подписке и VPN-конфигурациях пользователя.

    Attributes
        status (str): Статус подписки ('active', 'inactive', 'no_subscription').
        subscription_type (Optional[str]): Тип подписки (например, 'PREMIUM').
        remaining (str): Количество оставшихся дней подписки или 'UNLIMITED'.
        configs (List[SVPNConfig]): Список VPN-конфигов пользователя.
        end_date (Optional[datetime]): Дата окончания подписки.

    """

    status: str
    subscription_type: str | None
    remaining: str
    configs: list[SVPNConfig]
    end_date: datetime | None

    @field_serializer("end_date")
    def serialize_end_date(self, value: datetime | None) -> str | None:
        """Сериализация даты окончания подписки в строку формата YYYY-MM-DD.

        Args:
           value (Optional[datetime]): Дата окончания подписки.

        Returns
           Optional[str]: Строка с датой в формате YYYY-MM-DD или None.

        """
        if value is None:
            return None
        return value.strftime("%Y-%m-%d")
