from typing import Any
from uuid import UUID

from loguru import logger

from bot.integrations.api_client import APIClient
from bot.payment.providers.payment_client import BasePaymentProvider
from bot.payment.schemas import (
    SAttachProviderPaymentIn,
    SCancelPaymentIn,
    SConfirmPaymentIn,
    SConfirmPaymentResponse,
    SCreateManualPaymentTransactionIn,
    SPaymentTransactionResponse,
)


# TODO ДОкументация тесты типы данных логирование
class PaymentAPIAdapter:
    """Адаптер для работы с Payment API.

    Инкапсулирует HTTP-вызовы и преобразование DTO → Pydantic схемы.

    Attributes
        _client: HTTP-клиент для взаимодействия с API.

    """

    def __init__(self, client: APIClient, provider: BasePaymentProvider) -> None:
        """Инициализация адаптера.

        Args:
            client: HTTP клиент для взаимодействия с внешним API.
            provider: Платёжный провайдер (не используется адаптером напрямую,
                хранится для совместимости с местом вызова).

        """
        self._client = client

    async def create_transaction(
        self,
        amount: int,
        subscription_months: int,
        is_premium: bool,
        is_founder: bool,
    ) -> SPaymentTransactionResponse:
        """Создаёт платёжную транзакцию.

        Args:
            amount: Сумма платежа в минимальных единицах (например, копейки).
            subscription_months: Количество месяцев подписки.
            is_premium: Флаг премиум-подписки.
            is_founder: Флаг пользователя-основателя.

        Returns
            SPaymentTransactionResponse: Данные созданной транзакции.

        Raises
            Exception: Ошибка HTTP-клиента или валидации ответа API.

        """
        logger.info(
            "Создаёт платёжную транзакцию: amount={} months={} premium={} founder={}",
            amount,
            subscription_months,
            is_premium,
            is_founder,
        )
        payload = SCreateManualPaymentTransactionIn(
            amount=amount,
            currency="RUB",
            subscription_months=subscription_months,
            is_premium=is_premium,
            is_founder=is_founder,
        )
        data, status_code = await self._client.post(
            "/payment/transaction",
            json=payload.model_dump(),
        )
        result = SPaymentTransactionResponse.model_validate(data)
        logger.debug("Транзакция создана: id={} status={}", result.id, result.status)

        return result

    async def attach_provider_payment(
        self,
        transaction_id: UUID,
        gateway_transaction_id: str,
        gateway_payload: dict[Any, Any] | None,
    ) -> SPaymentTransactionResponse:
        """Привязывает provider transaction к внутренней транзакции.

        Args:
            transaction_id: UUID внутренней транзакции.
            gateway_transaction_id: ID транзакции внешнего платёжного шлюза.
            gateway_payload: Сырые данные платежа от шлюза.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        Raises
            Exception: Ошибка HTTP-клиента или валидации ответа.

        """
        logger.info(
            "Привязка provider payment: transaction_id={} gateway_id={}",
            transaction_id,
            gateway_transaction_id,
        )

        payload = SAttachProviderPaymentIn(
            # transaction_id=transaction_id,
            gateway_transaction_id=gateway_transaction_id,
            gateway_payload=gateway_payload,
        )

        data, status_code = await self._client.post(
            f"/payment/transaction/{transaction_id}/provider",
            json=payload.model_dump(mode="json"),
        )
        result = SPaymentTransactionResponse.model_validate(data)

        logger.debug(
            "Provider payment привязан: transaction_id={} status={}",
            result.id,
            result.status,
        )

        return result

    async def mark_payment_started(
        self, transaction_id: UUID
    ) -> SPaymentTransactionResponse:
        """Помечает транзакцию как оплаченную пользователем (ожидает подтверждения).

        Args:
            transaction_id: UUID транзакции.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        """
        data, _ = await self._client.post(
            f"/payment/transaction/{transaction_id}/paid", json={}
        )
        return SPaymentTransactionResponse.model_validate(data)

    async def confirm_transaction(
        self,
        transaction_id: UUID,
    ) -> SConfirmPaymentResponse:
        """Подтверждает платёжную транзакцию.

        Args:
            transaction_id: UUID транзакции.

        Returns
            SConfirmPaymentResponse: Результат подтверждения.

        """
        logger.info("Подтверждение прихода денег (админом): {}", transaction_id)
        payload = SConfirmPaymentIn(transaction_id=transaction_id)
        data, status_code = await self._client.post(
            "/payment/transaction/admin/confirm",
            json=payload.model_dump(mode="json"),
        )
        result = SConfirmPaymentResponse.model_validate(data)
        logger.debug(
            "Транзакция подтверждена: id={} status={}",
            result.transaction_res.id,
            result.transaction_res.status,
        )
        return result

    async def webhook_confirm_transaction(
        self,
        transaction_id: UUID,
    ) -> SConfirmPaymentResponse:
        """Подтверждает платёжную транзакцию по вебхуку платёжного провайдера.

        Args:
            transaction_id: UUID транзакции.

        Returns
            SConfirmPaymentResponse: Результат подтверждения.

        """
        logger.info("Подтверждение прихода денег (вебхук): {}", transaction_id)
        payload = SConfirmPaymentIn(transaction_id=transaction_id)
        data, status_code = await self._client.post(
            "/payment/transaction/webhook/confirm",
            json=payload.model_dump(mode="json"),
        )
        result = SConfirmPaymentResponse.model_validate(data)
        logger.debug(
            "Транзакция подтверждена: id={} status={}",
            result.transaction_res.id,
            result.transaction_res.status,
        )
        return result

    async def cancel_transaction(
        self,
        transaction_id: UUID,
    ) -> SPaymentTransactionResponse:
        """Отменяет платёжную транзакцию (по действию пользователя/админа).

        Args:
            transaction_id: UUID транзакции.

        Returns
            SPaymentTransactionResponse: Данные отменённой транзакции.

        """
        logger.info("Процесс отмены созданной транзакции: {}", transaction_id)
        payload = SCancelPaymentIn(transaction_id=transaction_id)
        data, status_code = await self._client.post(
            "/payment/transaction/cancel",
            json=payload.model_dump(mode="json"),
        )
        result = SPaymentTransactionResponse.model_validate(data)
        logger.debug("Транзакция отменена: id={} status={}", result.id, result.status)
        return result

    async def webhook_cancel_transaction(
        self,
        transaction_id: UUID,
    ) -> SPaymentTransactionResponse:
        """Отменяет платёжную транзакцию по вебхуку платёжного провайдера.

        В отличие от `cancel_transaction`, не требует Telegram-контекста
        пользователя — вебхук приходит от платёжного шлюза напрямую, а не
        от бота от имени конкретного пользователя (см. `X-Telegram-Id` в
        `APIClient._build_headers`, который в этом случае взять неоткуда).

        Args:
            transaction_id: UUID транзакции.

        Returns
            SPaymentTransactionResponse: Данные отменённой транзакции.

        """
        logger.info("Отмена транзакции по вебхуку: {}", transaction_id)
        payload = SCancelPaymentIn(transaction_id=transaction_id)
        data, status_code = await self._client.post(
            "/payment/transaction/webhook/cancel",
            json=payload.model_dump(mode="json"),
        )
        result = SPaymentTransactionResponse.model_validate(data)
        logger.debug("Транзакция отменена: id={} status={}", result.id, result.status)
        return result

    async def get_by_gateway_id(
        self, gateway_transaction_id: str
    ) -> SPaymentTransactionResponse:
        """Находит транзакцию по ID платежа во внешнем шлюзе.

        Args:
            gateway_transaction_id: ID транзакции внешнего платёжного шлюза.

        Returns
            SPaymentTransactionResponse: Найденная транзакция.

        """
        logger.debug(
            "Поиск транзакции по gateway_transaction_id={}", gateway_transaction_id
        )
        data = await self._client.get(
            "/payment/transaction",
            params={"gateway_transaction_id": gateway_transaction_id},
        )
        result = SPaymentTransactionResponse.model_validate(data)
        logger.debug("Транзакция найдена: id={} status={}", result.id, result.status)

        return result
