from uuid import UUID

from loguru import logger

from bot.integrations.api_client import APIClient
from bot.payment.schemas import (
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

    def __init__(self, client: APIClient) -> None:
        """Инициализация адаптера.

        Args:
            client: HTTP клиент для взаимодействия с внешним API.

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
            "Создаёт платёжную транзакцию: amount=%s months=%s premium=%s founder=%s",
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
        logger.debug("Транзакция создана, status=%s response=%s", status_code, data)
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
        logger.info("Подтверждение прихода денег: %s", transaction_id)
        payload = SConfirmPaymentIn(transaction_id=transaction_id)
        data, status_code = await self._client.post(
            "/payment/transaction/confirm",
            json=payload.model_dump(mode="json"),
        )
        logger.debug(
            "Транзакция подтверждена, status=%s response=%s", status_code, data
        )
        return SConfirmPaymentResponse.model_validate(data)

    async def cancel_transaction(
        self,
        transaction_id: UUID,
    ) -> SPaymentTransactionResponse:
        """Отменяет платёжную транзакцию.

        Args:
            transaction_id: UUID транзакции.

        Returns
            SPaymentTransactionResponse: Данные отменённой транзакции.

        """
        logger.info("Процесс отмены созданной транзакции: %s", transaction_id)
        payload = SCancelPaymentIn(transaction_id=transaction_id)
        data, status_code = await self._client.post(
            "/payment/transaction/cancel",
            json=payload.model_dump(mode="json"),
        )
        logger.debug("Транзакция отменена, status=%s response=%s", status_code, data)
        return SPaymentTransactionResponse.model_validate(data)
