# import asyncio
# import hashlib
# import hmac
# import json
# from decimal import Decimal
# from pprint import pprint
#
# import httpx
# from bot.payment.dto import CreatePaymentDTO, CreatedPaymentDTO, PaymentWebhookDTO
# from bot.payment.dto import PaymentStatus
#
#
# class PlategaProvider:
#     BASE_URL = "https://app.platega.io/"
#
#     def __init__(
#             self,
#             merchant_id: str,
#             secret_key: str,
#     ):
#         self.merchant_id = merchant_id
#         self.secret_key = secret_key
#
#         self.client = httpx.AsyncClient(
#             base_url=self.BASE_URL,
#             timeout=15,
#             headers={
#                 "X-MerchantId": self.merchant_id,
#                 "X-Secret": self.secret_key,
#                 "Content-Type": "application/json",
#             },
#         )
#
#     async def create_payment(
#             self,
#             data: CreatePaymentDTO,
#     ) -> CreatedPaymentDTO:
#
#         payload = {
#             # "paymentMethod": 11,
#             "paymentDetails": {
#                 "amount": float(data.amount),
#                 "currency": data.currency,
#             },
#             "description": data.description,
#             "return": data.success_url,
#             "failedUrl": data.failed_url,
#             "payload": data.order_id,
#         }
#
#         response = await self.client.post(
#             "v2/transaction/process",
#             json=payload,
#         )
#
#         response.raise_for_status()
#
#         response_data = response.json()
#         status = PaymentStatus.PENDING if response_data["status"].lower() == PaymentStatus.PENDING else PaymentStatus.FAILED
#         return CreatedPaymentDTO(
#             provider_payment_id=response_data["transactionId"],
#             payment_url=response_data["url"],
#             expires_at=response_data["expiresIn"],
#             rate=response_data["rate"],
#             status=status
#
#         )
#
#     async def verify_webhook(
#             self,
#             merchant_id: str | None,
#             secret: str | None,
#     ) -> bool:
#
#         if not merchant_id or not secret:
#             return False
#
#         return (
#                 merchant_id == self.merchant_id
#                 and secret == self.secret_key
#         )
#
#     async def parse_webhook(
#             self,
#             body: bytes,
#     ) -> PaymentWebhookDTO:
#
#         data = json.loads(body)
#
#         provider_status = data["status"]
#
#         if provider_status == "CONFIRMED":
#             status = "paid"
#
#         elif provider_status in (
#                 "CANCELED",
#                 "CHARGEBACKED",
#         ):
#             status = "failed"
#
#         else:
#             status = "pending"
#
#         return PaymentWebhookDTO(
#             provider_payment_id=data["id"],
#             status=status,
#             raw_data=data,
#         )
#
#     async def close(self) -> None:
#         await self.client.aclose()
#
#
# if __name__ == '__main__':
#     async def main():
#         cr_payment = CreatePaymentDTO(
#             amount=Decimal(100),
#             currency="RUB",
#             order_id="rr123rr",
#             description="test payment",
#             success_url="https://example.com",
#             failed_url="https://example.com",
#             payload="payload",
#         )
#         client = PlategaProvider(
#             secret_key="arWQSJS1uL7AMHvzZNDcTiDOXW4d03jRc6vWGZoPIje38wCAkOLFbaiYe2ZRi0SrTvaiewswg9o9oIg4hkj0iZkiUpTDkP4mNnui",
#             merchant_id="e6157015-e7e9-48be-b65e-1bb5932326dc",
#         )
#
#         res = await client.create_payment(data=cr_payment)
#         pprint(res)
#
#
#     asyncio.run(main())
