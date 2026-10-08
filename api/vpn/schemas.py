from pydantic import BaseModel

from shared.enums.vpn_enum import VPNBackend


class SVPNCreateRequest(BaseModel):
    """Схема запроса на создание нового VPN-конфига.

    Attributes
        tg_id (int): Telegram ID пользователя.
        file_name (str): Имя файла конфигурации VPN.
        pub_key (str): Публичный ключ пользователя.
        node_name (str | None): Имя ноды/локации (ключ в settings_bot.vpn.nodes).
        backend (VPNBackend | None): Бэкенд конфига.
        protocol (str | None): Протокол/версия внутри бэкенда — одно или
            несколько значений `VPNProtocol` через запятую (у XRay-подписки
            это несколько inbound сразу).
        config_ids (list[str] | None): Для XRay — uuid клиентов на панели.

    """

    tg_id: int
    file_name: str
    pub_key: str
    node_name: str | None = None
    backend: VPNBackend | None = None
    protocol: str | None = None
    config_ids: list[str] | None = None


class SVPNCreateResponse(BaseModel):
    """Схема ответа после успешного создания VPN-конфига.

    Attributes
        file_name (str): Имя созданного файла конфигурации.
        pub_key (str): Публичный ключ пользователя.

    """

    file_name: str
    pub_key: str


class SVPNDeleteRequest(SVPNCreateResponse):
    """Запрос на удаление файла конфигурации."""

    ...


class SVPNDeleteResponse(BaseModel):
    """Ответ на удаление файла конфигурации."""

    deleted: int


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
