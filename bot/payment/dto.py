from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from shared.enums.payment_enum import PaymentStatus


@dataclass(slots=True)
class CreatePaymentDTO:
    """Данные для создания платежа у провайдера.

    Attributes
        amount: Сумма платежа в рублях — целое число, не копейки (см.
            #261). Тот же домен значений, что у `api/payment/model.py`
            (`Mapped[int]`) и `api/payment/schemas.py` (`Field(gt=0)`) —
            решение продуктовое: копейки сейчас не нужны, поэтому тип
            един по всем слоям, а не `Decimal`, который обнулялся бы
            приведением к `float` перед отправкой провайдеру.

    """

    amount: int
    currency: str
    order_id: str
    description: str
    success_url: str | None = None
    failed_url: str | None = None
    payload: str | None = None

    def __post_init__(self) -> None:
        """Проверяет положительность суммы — не только на границе api."""
        if self.amount <= 0:
            raise ValueError(
                f"amount должен быть положительным, получено {self.amount}"
            )


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
            Тип `Decimal`, а не `int` (см. #293): формат этого поля
            провайдером не документирован, и округление до целого рубля на
            границе разбора пропустило бы расхождение меньше рубля
            (`149.50` от провайдера против `149` в транзакции совпали бы
            после `int()`). Домен "целые рубли" (#261) относится к суммам,
            которые создаёт сама система — на этой границе формат нам не
            принадлежит.
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
