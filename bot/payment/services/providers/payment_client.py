# from typing import Protocol
#
# from bot.payment.dto import CreatePaymentDTO, CreatedPaymentDTO, PaymentWebhookDTO
#
#
# class BasePaymentProvider(Protocol):
#     async def create_payment(
#         self,
#         data: CreatePaymentDTO,
#     ) -> CreatedPaymentDTO:
#         ...
#
#     async def verify_webhook(
#         self,
#         body: bytes,
#         signature: str | None,
#     ) -> bool:
#         ...
#
#     async def parse_webhook(
#         self,
#         body: bytes,
#     ) -> PaymentWebhookDTO:
#         ...
