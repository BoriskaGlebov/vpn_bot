from dataclasses import dataclass


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

    """

    id: int
    remark: str
    enable: bool
    port: int
