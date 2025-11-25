from sqlalchemy.ext.asyncio import AsyncSession

from bot.dao.base import BaseDAO
from bot.subscription.models import Subscription, SubscriptionType
from bot.users.schemas import SUserTelegramID


class SubscriptionDAO(BaseDAO[Subscription]):
    """Класс DAO для работы с подписками пользователей.

    Обеспечивает операции с таблицей `subscriptions`, позволяя создавать,
    обновлять и получать подписки пользователей через ORM.

    Attributes
        model (type[Subscription]): Модель ORM, с которой работает DAO.
            Используется для всех стандартных операций CRUD, предоставляемых
            `BaseDAO`.

    """

    model = Subscription

    @classmethod
    async def activate_subscription(
        self,
        session: AsyncSession,
        stelegram_id: SUserTelegramID,
        days: int | None = None,
        month: int | None = None,
        sub_type: SubscriptionType = SubscriptionType.STANDARD,
    ) -> Subscription:
        pass
