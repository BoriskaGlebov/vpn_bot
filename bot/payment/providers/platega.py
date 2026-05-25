import asyncio
import json
from decimal import Decimal
from pprint import pprint

import httpx

from bot.core.config import settings_bot
from bot.payment.dto import (
    CreatedPaymentDTO,
    CreatePaymentDTO,
    PaymentStatus,
    PaymentWebhookDTO,
)


class PlategaProvider:
    BASE_URL = "https://app.platega.io"

    def __init__(
        self,
        merchant_id: str,
        secret_key: str,
    ) -> None:
        self.merchant_id = merchant_id
        self.secret_key = secret_key

        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=15,
            headers={
                "X-MerchantId": self.merchant_id,
                "X-Secret": self.secret_key,
                "Content-Type": "application/json",
            },
        )

    async def create_payment(
        self,
        data: CreatePaymentDTO,
    ) -> CreatedPaymentDTO:
        payload = {
            # "paymentMethod": 11,
            "paymentDetails": {
                "amount": float(data.amount),
                "currency": data.currency,
            },
            "description": data.description,
            "return": data.success_url,
            "failedUrl": data.failed_url,
            "payload": data.order_id,
        }

        response = await self.client.post(
            "v2/transaction/process",
            json=payload,
        )

        response.raise_for_status()

        response_data = response.json()
        status = (
            PaymentStatus.PENDING
            if response_data["status"].lower() == PaymentStatus.PENDING
            else PaymentStatus.FAILED
        )
        return CreatedPaymentDTO(
            provider_payment_id=response_data["transactionId"],
            payment_url=response_data["url"],
            expires_at=response_data["expiresIn"],
            rate=response_data["rate"],
            status=status,
        )

    async def verify_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
    ) -> bool:
        merchant_id = headers.get("X-MerchantId")
        secret = headers.get("X-Secret")
        if not merchant_id or not secret:
            return False

        return merchant_id == self.merchant_id and secret == self.secret_key

    async def parse_webhook(
        self,
        body: bytes,
    ) -> PaymentWebhookDTO:
        data = json.loads(body)

        provider_status = data["status"]

        if provider_status == "CONFIRMED":
            status = PaymentStatus.PAID

        elif provider_status in (
            "CANCELED",
            "CHARGEBACKED",
        ):
            status = PaymentStatus.FAILED

        else:
            status = PaymentStatus.PENDING

        return PaymentWebhookDTO(
            provider_payment_id=data["id"],
            status=status,
            raw_data=data,
        )

    async def close(self) -> None:
        await self.client.aclose()


if __name__ == "__main__":

    async def main():
        cr_payment = CreatePaymentDTO(
            amount=Decimal(10),
            currency="RUB",
            order_id="rr123rr",
            description="test payment",
            success_url="https://e9fe-144-31-59-183.ngrok-free.app/bot/payment-webhook",
            failed_url="https://e9fe-144-31-59-183.ngrok-free.app/bot/payment-webhook",
            payload="payload",
        )
        client = PlategaProvider(
            secret_key=settings_bot.payment.api_key.get_secret_value(),
            merchant_id=settings_bot.payment.merchant_id.get_secret_value(),
        )

        res = await client.create_payment(data=cr_payment)
        pprint(res)

    asyncio.run(main())
