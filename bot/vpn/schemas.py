from pydantic import BaseModel, ConfigDict


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


class SVPNDeleteRequest(SVPNCreateResponse):
    """Запрос на удаление файла."""

    ...


class SVPNDeleteResponse(BaseModel):
    """Ответ на удаление файла."""

    deleted: int


class S3XuiCredentials(BaseModel):
    """DTO с учётными данными администратора 3x-ui панели.

    Используется для авторизации в API панели.
    """

    username: str
    password: str


class S3XuiUSerSettings(BaseModel):
    """DTO настроек пользователя для создания клиента в 3x-ui.

    Описывает параметры VPN-пользователя, включая ограничения,
    срок действия и идентификаторы подписки.
    """

    id: str
    email: str
    tgId: int
    subId: str

    flow: str = ""

    limitIp: int = 0
    totalGB: int = 0
    expiryTime: int = 0
    reset: int = 0

    enable: bool = True

    comment: str = ""
    model_config = ConfigDict(from_attributes=True)
