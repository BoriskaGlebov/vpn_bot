from pydantic import BaseModel


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
