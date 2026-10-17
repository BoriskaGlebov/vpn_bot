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
    """Событие вебхука от платёжного провайдера.

    Attributes
        amount: Сумма платежа, присланная провайдером в вебхуке (см. #257) —
            `None`, если провайдер её не прислал (например, статусы
            CANCELED/CHARGEBACKED у Platega приходят без неё). Сверяется с
            суммой транзакции в БД перед подтверждением оплаты — иначе
            решение "платёж прошёл" принимается по одной строке статуса.

    """

    provider_payment_id: str
    status: PaymentStatus
    raw_data: dict[str, Any]

    amount: Decimal | None = None
    payload: str | None = None
