from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import SubscriptionInfoStatus, TrialStatus


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
    """Схема подписки пользователя."""

    user_id: int = Field(..., description="User ID")
    model_config = ConfigDict(from_attributes=True)


class SVPNConfig(BaseModel):
    """Схема информации о VPN-конфиге.

    Attributes
        file_name (str): Имя файла конфигурации.
        node_name (str | None): Имя ноды/локации (ключ в settings_bot.vpn.nodes).
        created_at (datetime): Дата и время создания конфига.

    """

    file_name: str
    node_name: str | None = None
    created_at: datetime


class SSubscriptionInfo(BaseModel):
    """Схема информации о подписке и VPN-конфигурациях пользователя.

    `api/` отдаёт данные — число, перечисление, дату, а не готовый текст для
    показа пользователю (см. #282): текст на русском (склонения, "дней"/
    "UNLIMITED") собирает бот, у которого для этого есть `settings_bot.messages`.

    Attributes
        status (SubscriptionInfoStatus): Статус подписки.
        subscription_type (Optional[str]): Тип подписки (например, 'PREMIUM').
        remaining (int | None): Количество оставшихся дней или None для
            бессрочной подписки.
        configs (List[SVPNConfig]): Список VPN-конфигов пользователя.
        end_date (Optional[datetime]): Дата окончания подписки.

    """

    status: SubscriptionInfoStatus
    subscription_type: str | None
    remaining: int | None
    configs: list[SVPNConfig]
    end_date: datetime | None
