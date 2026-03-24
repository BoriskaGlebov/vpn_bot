import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    ReferralBonusAlreadyGivenError,
    ReferralNotFoundError,
)
from api.referrals.dao import ReferralDAO
from api.subscription.dao import SubscriptionDAO
from api.subscription.models import SubscriptionType
from api.users.dao import UserDAO
from shared.schemas.referral import SReferralByInvite
from shared.schemas.users import SUserOut, SUserTelegramID


class ReferralService:
    """Сервис для работы с реферальной системой.

    Отвечает за регистрацию приглашений и начисление бонусов за приглашенных пользователей.
    """

    async def register_referral(
        self,
        session: AsyncSession,
        invited_user: SUserOut,
        inviter_telegram_id: int | None,
    ) -> None:
        """Регистрирует приглашение нового пользователя.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            invited_user (SUserOut): Данные приглашенного пользователя.
            inviter_telegram_id (Optional[int]): Telegram ID пригласителя.
                Если None, регистрация не производится.

        Returns
            None: Метод не возвращает значения.

        """
        if not inviter_telegram_id or invited_user.has_used_trial:
            return
        s_user = SUserTelegramID(telegram_id=inviter_telegram_id)
        inviter_model = await UserDAO.find_one_or_none(session=session, filters=s_user)
        if not inviter_model:
            return

        await ReferralDAO.add_referral(
            session=session, inviter_id=inviter_model.id, invited_id=invited_user.id
        )

    async def grant_referral_bonus(
        self, session: AsyncSession, invited_user: SUserOut, months: int = 1
    ) -> tuple[bool, int | None]:
        """Начисляет бонус пригласителю за регистрацию нового пользователя.

        Метод выполняет следующие шаги:
            1. Проверяет наличие реферальной записи для приглашенного пользователя.
            2. Проверяет, был ли уже начислен бонус.
            3. Если пригласитель не имеет активной подписки, создаёт стандартную.
               Иначе продлевает текущую подписку на указанное количество месяцев.
            4. Отмечает факт начисления бонуса и сохраняет дату.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            invited_user (SUserOut): Объект данных пользователя, который был приглашен.
            months (int, optional): Количество месяцев подписки, которое будет начислено.
                По умолчанию 1.

        Returns
            Tuple[bool, Optional[int]]:
                - bool: True, если бонус успешно начислен, False — если бонус уже начислен
                  или приглашение не найдено.
                - Optional[int]: Telegram ID пригласителя, если бонус был начислен, иначе None.

        """
        s_referral = SReferralByInvite(invited_id=invited_user.id)
        referral = await ReferralDAO.find_one_or_none(
            session=session, filters=s_referral
        )

        if not referral:
            logger.info(
                f"У пользователя не было приглашения {invited_user.telegram_id}"
            )
            raise ReferralNotFoundError(invited_user.telegram_id)

        if referral.bonus_given:
            logger.info(
                f"Бонус за друга уже начислен пользователю {invited_user.telegram_id}"
            )
            raise ReferralBonusAlreadyGivenError(invited_user.telegram_id)

        inviter = referral.inviter
        current_sub = inviter.current_subscription
        if current_sub is None:
            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=SUserTelegramID(telegram_id=inviter.telegram_id),
                month=months,
                sub_type=SubscriptionType.STANDARD,
            )
        else:
            current_sub.extend(months=months)
            await session.flush()

        referral.bonus_given = True
        referral.bonus_given_at = datetime.datetime.now(datetime.UTC)

        await session.flush()
        logger.info(
            f"Бонус за подписчика предоставлен: inviter={inviter.telegram_id}, invited={invited_user.telegram_id}, months={months}"
        )
        return True, inviter.telegram_id
