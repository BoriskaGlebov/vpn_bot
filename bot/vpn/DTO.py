from dataclasses import dataclass

from shared.enums.vpn_enum import VPNProtocol


@dataclass
class Inbound:
    """Модель inbound-конфигурации XRay.

    Attributes
        id (int):
            Уникальный идентификатор inbound-конфига.

        remark (str):
            Человекочитаемое имя/описание inbound (используется в панели).

        enable (bool):
            Флаг активности inbound-конфига.
            True — включён, False — отключён.

        port (int):
            Порт, на котором работает inbound-соединение.

        protocol (VPNProtocol | None):
            Протокол этого inbound, если он сопоставлен с конфигурацией ноды
            (`SInbound.protocol`) — см. `ThreeXUIAdapter._get_inbound`. `None`
            для «сырых» inbound из `_get_all_inbounds`, которые не проверялись
            на принадлежность настроенному списку.

    """

    id: int
    remark: str
    enable: bool
    port: int
    protocol: VPNProtocol | None = None


@dataclass
class UserUUID:
    """DTO для хранения UUID конфигурации пользователя.

    Используется как типизированная обёртка над идентификатором конфигурации VPN-пользователя.
    Позволяет унифицировать передачу UUID между слоями системы (сервисами, адаптерами и хранилищем).

    Attributes
        conf_uuid (str): UUID конфигурации пользователя в строковом формате.
            Используется для идентификации записи в системе управления VPN.

    Notes
        - Класс не содержит бизнес-логики.
        - Предназначен только для структурированной передачи данных.

    """

    conf_uuid: str
