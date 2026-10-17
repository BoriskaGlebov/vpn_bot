from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from shared.enums.payment_enum import PaymentStatus


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
        is_chargeback: Возврат уже полученных средств плательщику.
            Выражено явным полем DTO (см. #259), а не разбором
            `raw_data["status"] == "CHARGEBACKED"` в сервисном слое —
            сервис не должен знать конкретные строки провайдера.
        is_unknown_status: Провайдер прислал статус, не входящий в
            известный набор (CONFIRMED/CANCELED/CHARGEBACKED) — см. #259.
            Событие трактуется как PENDING, но в отличие от обычного
            "платёж пока не завершён" требует внимания администратора:
            если это новый терминальный статус Platega, транзакция иначе
            навсегда останется в PENDING без единого уведомления.

    """

    provider_payment_id: str
    status: PaymentStatus
    raw_data: dict[str, Any]

    amount: Decimal | None = None
    payload: str | None = None
    is_chargeback: bool = False
    is_unknown_status: bool = False
