from bot.integrations.api_client import APIClient
from bot.promo.schemas import SPromoValidateIn, SPromoValidationResult


class PromoAPIAdapter:
    """Клиент для работы с promo API."""

    def __init__(self, client: APIClient) -> None:
        self.client = client

    async def validate_code(
        self, code: str, base_amount: int
    ) -> SPromoValidationResult:
        """Проверяет промокод и получает расчёт скидки для текущего пользователя.

        Args:
            code: Код промокода, введённый пользователем.
            base_amount: Базовая цена подписки (до скидки).

        Returns
            SPromoValidationResult: Данные промокода и рассчитанная скидка.

        """
        payload = SPromoValidateIn(code=code, base_amount=base_amount)
        data, _ = await self.client.post(
            "/promo/validate",
            json=payload.model_dump(),
        )
        return SPromoValidationResult.model_validate(data)
