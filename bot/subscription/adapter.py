from bot.integrations.api_client import APIClient
from bot.subscription.schemas import (
    ActivateSubscriptionRequest,
    SSubscriptionCheck,
    STrialActivate,
    STrialActivateResponse,
)
from bot.users.schemas import SUserOut

type HTTPStatus = int


class SubscriptionAPIAdapter:
    """Адаптер для работы с Subscription API.

    Инкапсулирует HTTP-вызовы и преобразование DTO → Pydantic схемы.

    """

    def __init__(self, client: APIClient) -> None:
        """Инициализация Адаптера.

        Args:
            client: HTTP клиент для взаимодействия с API.

        """
        self._client = client

    async def check_premium(self, tg_id: int) -> SSubscriptionCheck:
        """Проверяет наличие активной премиум-подписки пользователя.

        Args:
            tg_id: Telegram ID пользователя.

        Returns
            SSubscriptionCheck: статус подписки, роль и активность.

        """
        data = await self._client.get(
            "/subscriptions/check/premium",
            params={"tg_id": tg_id},
        )

        return SSubscriptionCheck.model_validate(data)

    async def activate_trial(
        self, tg_id: int, days: int = 7
    ) -> tuple[STrialActivateResponse, HTTPStatus]:
        """Активирует пробный период подписки.

        Args:
            tg_id: Telegram ID пользователя.
            days: длительность trial в днях.

        Returns
            tuple:
                - STrialActivateResponse: результат активации
                - int: HTTP status code

        """
        payload = STrialActivate(tg_id=tg_id, days=days)
        data, status = await self._client.post(
            "/subscriptions/trial/activate", json=payload.model_dump()
        )

        return STrialActivateResponse.model_validate(data), status

    async def activate_paid(
        self,
        tg_id: int,
        months: int,
        premium: bool,
    ) -> SUserOut:
        """Активирует или продлевает платную подписку пользователя.

        Args:
            tg_id: Telegram ID пользователя.
            months: количество месяцев подписки.
            premium: тип подписки (True → PREMIUM, False → STANDARD).

        Returns
            SUserOut: обновлённый пользователь.

        """
        payload = ActivateSubscriptionRequest(
            tg_id=tg_id, months=months, premium=premium
        )
        data, _ = await self._client.post(
            "/subscriptions/activate", json=payload.model_dump()
        )
        return SUserOut.model_validate(data)
