import json
from collections.abc import Mapping

import httpx
from loguru import logger

from bot.payment.dto import (
    CreatedPaymentDTO,
    CreatePaymentDTO,
    PaymentStatus,
    PaymentWebhookDTO,
)


class PlategaProvider:
    """Платёжный провайдер Platega (`BasePaymentProvider`)."""

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
        """Создаёт платёж в Platega и возвращает ссылку на оплату.

        Args:
            data: Данные для создания платежа.

        Returns
            CreatedPaymentDTO: Ссылка на оплату и статус платежа.

        Raises
            httpx.HTTPError: При ошибке запроса к Platega (сеть, статус >= 400).

        """
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

        try:
            response = await self.client.post(
                "v2/transaction/process",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception(
                "Ошибка создания платежа в Platega: order_id={} amount={}",
                data.order_id,
                data.amount,
            )
            raise

        response_data = response.json()
        status = (
            PaymentStatus.PENDING
            if response_data["status"].lower() == PaymentStatus.PENDING
            else PaymentStatus.FAILED
        )
        logger.info(
            "Платёж создан в Platega: order_id={} provider_payment_id={} status={}",
            data.order_id,
            response_data["transactionId"],
            status,
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
        headers: Mapping[str, str],
        body: bytes,
    ) -> bool:
        """Проверяет подлинность вебхука по merchant ID и секретному ключу в заголовках.

        Args:
            headers: Заголовки входящего HTTP-запроса.
            body: Тело запроса (не используется — подпись Platega живёт в заголовках).

        Returns
            bool: True, если merchant ID и секрет совпадают с настроенными.

        """
        merchant_id = headers.get("X-MerchantId")
        secret = headers.get("X-Secret")
        if not merchant_id or not secret:
            logger.warning(
                "Вебхук Platega без X-MerchantId/X-Secret в заголовках — отклонён"
            )
            return False

        if merchant_id != self.merchant_id or secret != self.secret_key:
            logger.warning(
                "Вебхук Platega с неверной подписью (merchant_id={}) — отклонён",
                merchant_id,
            )
            return False

        return True

    async def parse_webhook(
        self,
        body: bytes,
    ) -> PaymentWebhookDTO:
        """Разбирает тело вебхука Platega в доменное событие.

        Args:
            body: Тело вебхука (JSON).

        Returns
            PaymentWebhookDTO: Разобранное событие с нормализованным статусом.

        """
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
            logger.debug(
                "Вебхук Platega с незнакомым статусом provider_status={} — "
                "трактуется как PENDING (provider_payment_id={})",
                provider_status,
                data["id"],
            )

        return PaymentWebhookDTO(
            provider_payment_id=data["id"],
            status=status,
            raw_data=data,
        )

    async def close(self) -> None:
        """Закрывает HTTP-клиент провайдера."""
        await self.client.aclose()
