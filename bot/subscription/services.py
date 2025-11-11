from sqlalchemy.ext.asyncio import AsyncSession

from bot.subscription.dao import SubscriptionDAO
from bot.users.schemas import SUserTelegramID


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, user_id: int, months: int
    ) -> None:
        """Активирует пробный период подписки."""
        schema_user = SUserTelegramID(telegram_id=user_id)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, days=months
        )

    @staticmethod
    async def activate_paid_subscription(
        session: AsyncSession, user_id: int, months: int
    ) -> None:
        """Активирует платную подписку после подтверждения оплаты."""
        schema_user = SUserTelegramID(telegram_id=user_id)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months
        )
