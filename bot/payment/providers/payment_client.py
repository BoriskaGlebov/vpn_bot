from typing import Protocol

from bot.payment.dto import CreatedPaymentDTO, CreatePaymentDTO, PaymentWebhookDTO


class BasePaymentProvider(Protocol):
    """Интерфейс платёжного провайдера (например, Platega)."""

    async def create_payment(
        self,
        data: CreatePaymentDTO,
    ) -> CreatedPaymentDTO:
        """Создаёт платёж у провайдера и возвращает ссылку на оплату."""
        ...

    async def verify_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
    ) -> bool:
        """Проверяет подлинность входящего вебхука провайдера."""
        ...

    async def parse_webhook(
        self,
        body: bytes,
    ) -> PaymentWebhookDTO:
        """Разбирает тело вебхука провайдера в доменное событие."""
        ...
