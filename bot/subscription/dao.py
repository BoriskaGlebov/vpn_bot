from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app_error.base_error import AppError, UserNotFoundError
from bot.config import logger
from bot.dao.base import BaseDAO
from bot.subscription.models import Subscription, SubscriptionType
from bot.users.dao import UserDAO
from bot.users.schemas import SSubscription, SUserTelegramID


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
        cls,
        session: AsyncSession,
        stelegram_id: SUserTelegramID,
        days: int | None = None,
        month: int | None = None,
        sub_type: SubscriptionType = SubscriptionType.STANDARD,
    ) -> Subscription:
        """Активирует подписку пользователя на указанное количество дней или месяцев.

        Аргументы
            session (AsyncSession): Асинхронная сессия SQLAlchemy для работы с базой данных.
            stelegram_id (SUserTelegramID): Идентификатор Telegram пользователя.
            days (Optional[int], optional): Количество дней для активации подписки. Defaults to None.
            month (Optional[int], optional): Количество месяцев для активации подписки. Defaults to None.
            sub_type (SubscriptionType): Тип подписки пользователя

        Raises
            ValueError: Если пользователь с указанным Telegram ID не найден.
            SQLAlchemyError: Если произошла ошибка при сохранении изменений в базе данных.

        Returns
            Subscription: Активированная подписка пользователя.

        """
        user = await UserDAO.find_one_or_none(session=session, filters=stelegram_id)
        if not user:
            logger.error(
                f"[DAO] Не удалось найти пользователя с {stelegram_id.telegram_id}"
            )
            raise UserNotFoundError(tg_id=stelegram_id.telegram_id)
        schema_subscription = SSubscription(user_id=user.id)
        subscription = await SubscriptionDAO.add(
            session=session, values=schema_subscription
        )
        try:
            async with cls.transaction(session=session):
                subscription.activate(days=days, month_num=month, sub_type=sub_type)
                logger.debug(f"[DAO] Активирую подписку на {days} дней")
                await session.commit()
                return subscription
        except AppError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при активации подписки: {e}")
            raise e
