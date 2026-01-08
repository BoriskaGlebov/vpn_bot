from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import logger
from bot.dao.base import BaseDAO
from bot.referrals.models import Referral


class ReferralDAO(BaseDAO[Referral]):
    """DAO для работы с таблицей рефералов."""

    model = Referral

    @classmethod
    async def add_referral(
        cls, session: AsyncSession, inviter_id: int, invited_id: int
    ) -> Referral:
        """Добавляет запись о новом приглашении в базу данных.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            inviter_id (int): ID пользователя, который пригласил.
            invited_id (int): ID приглашенного пользователя.

        Returns
            Referral: Созданный объект Referral.

        Raises
            SQLAlchemyError: Если произошла ошибка при добавлении записи.

        """
        try:
            referral = Referral(
                inviter_id=inviter_id,
                invited_id=invited_id,
                bonus_given=False,
                bonus_given_at=None,
            )
            session.add(referral)
            await session.flush()
            logger.info(
                f"[DAO] Зарегистрировано приглашение от пользователя: inviter={inviter_id}, invited={invited_id}"
            )
            return referral
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при добавлении записи: {e}")
            raise e
