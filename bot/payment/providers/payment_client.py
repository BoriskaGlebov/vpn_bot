from typing import Protocol

from bot.payment.dto import CreatedPaymentDTO, CreatePaymentDTO, PaymentWebhookDTO


class BasePaymentProvider(Protocol):
    async def create_payment(
        self,
        data: CreatePaymentDTO,
    ) -> CreatedPaymentDTO: ...

    async def verify_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
    ) -> bool: ...

    async def parse_webhook(
        self,
        body: bytes,
    ) -> PaymentWebhookDTO: ...
