from uuid import UUID

from bot.integrations.api_client import APIClient
from bot.subscription.schemas import (
    ActivateSubscriptionRequest,
    SSubscriptionCheck,
    SSubscriptionInfo,
    STrialActivate,
    STrialActivateResponse,
)
from bot.users.schemas import SUserOut
from bot.payment.schemas import SCreateManualPaymentTransactionIn, SPaymentTransactionResponse, SConfirmPaymentIn, \
    SCancelPaymentIn

type HTTPStatus = int

#TODO ДОкументация тесты типы данных логирование
class PaymentAPIAdapter:
    """Адаптер для работы с Subscription API.

    Инкапсулирует HTTP-вызовы и преобразование DTO → Pydantic схемы.

    """

    def __init__(self, client: APIClient) -> None:
        """Инициализация Адаптера.

        Args:
            client: HTTP клиент для взаимодействия с API.

        """
        self._client = client

    async def create_transaction(self,
                                 amount: int,
                                 subscription_months:int,
                                 is_premium: bool,
                                 is_founder: bool,
                                 ) -> SPaymentTransactionResponse:
        payload = SCreateManualPaymentTransactionIn(
            amount=amount,
            currency="RUB",
            subscription_months=subscription_months,
            is_premium=is_premium,
            is_founder=is_founder,

        )
        data,status_code = await self._client.post(
            "/payment/transaction",
            json=payload.model_dump(),
        )

        return SPaymentTransactionResponse.model_validate(data)

    async def confirm_transaction(self,
                                 transaction_id: UUID,
                                 ) -> SPaymentTransactionResponse:
        payload = SConfirmPaymentIn(
            transaction_id=transaction_id

        )
        data,status_code = await self._client.post(
            "/payment/transaction/confirm",
            json=payload.model_dump(mode="json"),
        )

        return SPaymentTransactionResponse.model_validate(data)

    async def cancel_transaction(self,
                                 transaction_id: UUID,
                                 ) -> SPaymentTransactionResponse:
        payload = SCancelPaymentIn(transaction_id=transaction_id)
        data,status_code = await self._client.post(
            "/payment/transaction/cancel",
            json=payload.model_dump(mode="json"),
        )

        return SPaymentTransactionResponse.model_validate(data)

    # async def activate_trial(
    #     self, tg_id: int, days: int = 7
    # ) -> tuple[STrialActivateResponse, HTTPStatus]:
    #     """Активирует пробный период подписки.
    #
    #     Args:
    #         tg_id: Telegram ID пользователя.
    #         days: длительность trial в днях.
    #
    #     Returns
    #         tuple:
    #             - STrialActivateResponse: результат активации
    #             - int: HTTP status code
    #
    #     """
    #     payload = STrialActivate(tg_id=tg_id, days=days)
    #     data, status = await self._client.post(
    #         "/subscriptions/trial/activate", json=payload.model_dump()
    #     )
    #
    #     return STrialActivateResponse.model_validate(data), status
    #
    # async def activate_paid(
    #     self,
    #     tg_id: int,
    #     months: int,
    #     premium: bool,
    # ) -> SUserOut:
    #     """Активирует или продлевает платную подписку пользователя.
    #
    #     Args:
    #         tg_id: Telegram ID пользователя.
    #         months: количество месяцев подписки.
    #         premium: тип подписки (True → PREMIUM, False → STANDARD).
    #
    #     Returns
    #         SUserOut: обновлённый пользователь.
    #
    #     """
    #     payload = ActivateSubscriptionRequest(
    #         tg_id=tg_id, months=months, premium=premium
    #     )
    #     data, _ = await self._client.post(
    #         "/subscriptions/activate", json=payload.model_dump()
    #     )
    #     return SUserOut.model_validate(data)
    #
    # async def get_subscription_info(
    #     self,
    #     tg_id: int,
    # ) -> SSubscriptionInfo:
    #     """Получает инфу о подписке."""
    #     data = await self._client.get(
    #         "/subscriptions/info",
    #         params={"tg_id": tg_id},
    #     )
    #
    #     return SSubscriptionInfo(**data)
