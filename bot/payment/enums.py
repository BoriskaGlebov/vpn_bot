from enum import Enum


class PaymentSource(str, Enum):
    """Источник создания платежа.

    Attributes
        MANUAL: Платеж подтвержден вручную администратором.
        GATEWAY: Платеж создан через платежный шлюз.

    """

    MANUAL = "MANUAL"
    GATEWAY = "GATEWAY"
