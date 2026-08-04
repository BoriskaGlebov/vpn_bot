from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.dao import UserDAO
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
        users_id = await UserDAO.get_telegram_ids_excluding_role(
            session=session, role_name=RoleEnum.ADMIN
        )
        logger.info("Получил id пользователей для рассылки.")
        return users_id
