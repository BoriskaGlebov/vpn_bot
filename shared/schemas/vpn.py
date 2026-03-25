from datetime import datetime

from pydantic import BaseModel, field_serializer


class SVPNCreateRequest(BaseModel):
    """Схема запроса на создание нового VPN-конфига.

    Attributes
        tg_id (int): Telegram ID пользователя.
        file_name (str): Имя файла конфигурации VPN.
        pub_key (str): Публичный ключ пользователя.

    """

    tg_id: int
    file_name: str
    pub_key: str


class SVPNCreateResponse(BaseModel):
    """Схема ответа после успешного создания VPN-конфига.

    Attributes
        file_name (str): Имя созданного файла конфигурации.
        pub_key (str): Публичный ключ пользователя.

    """

    file_name: str
    pub_key: str


class SVPNCheckLimitResponse(BaseModel):
    """Схема ответа при проверке лимита VPN-конфигов пользователя.

    Attributes
        can_add (bool): Может ли пользователь создать новый конфиг.
        limit (int): Максимальное количество конфигов для подписки.
        current (int): Текущее количество конфигов пользователя.

    """

    can_add: bool
    limit: int
    current: int


class SVPNConfig(BaseModel):
    """Схема информации о VPN-конфиге.

    Attributes
        file_name (str): Имя файла конфигурации.

    """

    file_name: str


class SVPNSubscriptionInfo(BaseModel):
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
