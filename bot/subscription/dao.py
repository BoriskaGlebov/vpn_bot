from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import logger
from bot.dao.base import BaseDAO
from bot.subscription.models import Subscription
from bot.users.dao import UserDAO
from bot.users.schemas import SSubscription, SUser, SUserTelegramID


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
    ) -> Subscription:
        """Активирует подписку пользователя на указанное количество дней или месяцев.

        Аргументы
            session (AsyncSession): Асинхронная сессия SQLAlchemy для работы с базой данных.
            stelegram_id (SUserTelegramID): Идентификатор Telegram пользователя.
            days (Optional[int], optional): Количество дней для активации подписки. Defaults to None.
            month (Optional[int], optional): Количество месяцев для активации подписки. Defaults to None.

        Raises
            ValueError: Если пользователь с указанным Telegram ID не найден.
            SQLAlchemyError: Если произошла ошибка при сохранении изменений в базе данных.

        Returns
            Subscription: Активированная подписка пользователя.

        """
        user = await UserDAO.find_one_or_none(session=session, filters=stelegram_id)
        SUser.model_validate(user)
        if not user:
            logger.error(f"Не удалось найти пользователя с {stelegram_id.telegram_id}")
            raise ValueError(
                f"Не удалось найти пользователя с {stelegram_id.telegram_id}"
            )
        schema_subscription = SSubscription(user_id=user.id)
        subscription = await SubscriptionDAO.find_one_or_none(
            session=session, filters=schema_subscription
        )
        if subscription is None:
            # Если нет подписки — создаём новую или кидаем ошибку
            subscription = Subscription(user_id=user.id)
            session.add(subscription)
        subscription.activate(days=days, month_num=month)
        try:
            logger.info(f"автивирую подписку на {days} дней")
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при активации подписки: {e}")
            raise e
        return subscription
