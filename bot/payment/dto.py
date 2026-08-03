from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


@dataclass(slots=True)
class CreatePaymentDTO:
    """Данные для создания платежа у провайдера."""

    amount: Decimal
    currency: str
    order_id: str
    description: str
    success_url: str | None = None
    failed_url: str | None = None
    payload: str | None = None


class PaymentStatus(str, Enum):
    """Статус платежа у провайдера."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


@dataclass(slots=True)
class CreatedPaymentDTO:
    """Результат создания платежа, полученный от провайдера."""

    provider_payment_id: str
    payment_url: str
    status: PaymentStatus
    expires_at: str | None = None
    rate: float | None = None


@dataclass(slots=True)
class PaymentWebhookDTO:
    """Событие вебхука от платёжного провайдера."""

    provider_payment_id: str
    status: PaymentStatus
    raw_data: dict[str, Any]

    payload: str | None = None
