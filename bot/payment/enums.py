from enum import Enum


class PaymentStatus(str, Enum):
    """Статус платежа.

    Attributes
        PENDING: Платеж создан, но еще не завершен.
        PAID: Платеж успешно завершен.
        FAILED: Платеж не прошел.
        CANCELED: Платеж отменен.

    """

    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class PaymentSource(str, Enum):
    """Источник создания платежа.

    Attributes
        MANUAL: Платеж подтвержден вручную администратором.
        GATEWAY: Платеж создан через платежный шлюз.

    """

    MANUAL = "MANUAL"
    GATEWAY = "GATEWAY"
