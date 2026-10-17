import json
import secrets
from collections.abc import Mapping

import httpx
from loguru import logger

from bot.payment.dto import CreatedPaymentDTO, CreatePaymentDTO, PaymentWebhookDTO
from bot.payment.exceptions import PaymentProviderError
from shared.enums.payment_enum import PaymentStatus


class PlategaProvider:
    """Платёжный провайдер Platega (`BasePaymentProvider`)."""

    provider_name = "Platega"
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
            PaymentProviderError: При ошибке запроса к Platega (сеть, статус >= 400).

        """
        payload = {
            # "paymentMethod": 11,
            "paymentDetails": {
                # float(int) здесь безопасно (#261) — amount целое число
                # рублей по всем слоям, без копеек; потери точности нет.
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
        except httpx.HTTPError as e:
            logger.exception(
                "Ошибка создания платежа в Platega: order_id={} amount={}",
                data.order_id,
                data.amount,
            )
            raise PaymentProviderError(
                message=f"Ошибка создания платежа в Platega (order_id={data.order_id})",
                cause=e,
            ) from e

        response_data = response.json()
        # Нормализация статуса провайдера сделана явно (#258) — сравнение не
        # должно зависеть от регистра значений PaymentStatus: с "PENDING"
        # (верхний регистр, как и у остальных статусов Platega) оно останется
        # корректным независимо от того, в каком регистре объявлены значения
        # самого enum.
        status = (
            PaymentStatus.PENDING
            if response_data["status"].upper() == "PENDING"
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

        if not secrets.compare_digest(
            merchant_id, self.merchant_id
        ) or not secrets.compare_digest(secret, self.secret_key):
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
        # int, не Decimal (#261) — сумма платежа везде целые рубли, без
        # копеек; сравнивается с tx.amount (int) при подтверждении (#257).
        amount = int(data["amount"]) if "amount" in data else None
        is_chargeback = False
        is_unknown_status = False

        if provider_status == "CONFIRMED":
            status = PaymentStatus.PAID

        elif provider_status == "CHARGEBACKED":
            status = PaymentStatus.FAILED
            is_chargeback = True

        elif provider_status == "CANCELED":
            status = PaymentStatus.FAILED

        else:
            status = PaymentStatus.PENDING
            is_unknown_status = True
            # warning, а не debug: это новый/незнакомый терминальный статус
            # Platega, а не штатное "платёж пока не завершён" — см. #259.
            # На debug сообщение не попадало бы в постоянные логи (там
            # уровень info), и о зависшей в PENDING транзакции никто не
            # узнал бы вовсе.
            logger.warning(
                "Вебхук Platega с незнакомым статусом provider_status={} — "
                "трактуется как PENDING, требует внимания (provider_payment_id={})",
                provider_status,
                data["id"],
            )

        return PaymentWebhookDTO(
            provider_payment_id=data["id"],
            status=status,
            raw_data=data,
            amount=amount,
            is_chargeback=is_chargeback,
            is_unknown_status=is_unknown_status,
        )

    async def close(self) -> None:
        """Закрывает HTTP-клиент провайдера."""
        await self.client.aclose()
