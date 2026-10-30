from bot.promo.adapter import PromoAPIAdapter
from bot.promo.schemas import SPromoValidationResult


class PromoService:
    """Сервис промокодов — предпросмотр скидки перед оплатой подписки.

    Фиксация применения (счётчик, запись об использовании) целиком на
    стороне api/ — происходит при подтверждении оплаты, а не здесь.
    """

    def __init__(self, adapter: PromoAPIAdapter) -> None:
        self.api_adapter = adapter

    async def validate_code(
        self, code: str, base_amount: int
    ) -> SPromoValidationResult:
        """Проверяет промокод и возвращает расчёт скидки.

        Args:
            code: Код промокода, введённый пользователем.
            base_amount: Базовая цена подписки (до скидки).

        Returns
            SPromoValidationResult: Данные промокода и рассчитанная скидка.

        Raises
            APIClientError: Код не найден, недействителен, лимит исчерпан
                либо уже применялся этим пользователем — текст причины в
                `error.message`.

        """
        return await self.api_adapter.validate_code(code=code, base_amount=base_amount)
