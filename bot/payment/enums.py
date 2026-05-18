from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class PaymentSource(str, Enum):
    MANUAL = "MANUAL"  # админ подтвердил
    GATEWAY = "GATEWAY"  # платежная система
