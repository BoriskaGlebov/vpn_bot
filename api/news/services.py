from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.models import Role, User
from shared.enums.admin_enum import RoleEnum


class NewsService:
    """Сервис для работы с новостной рассылкой через Telegram-бота."""

    async def get_users_for_news(self, session: AsyncSession) -> list[int]:
        """Получает список Telegram ID всех пользователей, кроме администраторов.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.

        Returns
            List[int]: Список Telegram ID пользователей для рассылки.

        """
        query = (
            select(User.telegram_id)
            .join(User.role)
            .where(Role.name != RoleEnum.ADMIN.value)
        )

        result = await session.execute(query)
        users_id = result.scalars().all()
        logger.info("Получил id пользователей для рассылки.")
        return list(users_id)
