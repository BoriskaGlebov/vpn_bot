from aiogram import Bot
from loguru._logger import Logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.users.models import Role, User


class NewsService:
    """Сервис для работы с новостной рассылкой через Telegram-бота.

    Attributes
        bot (Bot): Экземпляр бота Aiogram.
        logger (Logger): Логгер Loguru для записи информации и ошибок.

    """

    def __init__(self, bot: Bot, logger: Logger) -> None:
        self.bot = bot
        self.logger = logger

    async def all_users_id(self, session: AsyncSession) -> list[int]:
        """Получает список Telegram ID всех пользователей, кроме администраторов.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.

        Returns
            List[int]: Список Telegram ID пользователей для рассылки.

        """
        query = select(User.telegram_id).join(User.role).where(Role.name != "admin")
        result = await session.execute(query)
        users_id = result.scalars().all()
        self.logger.info("Получил id пользователей для рассылки.")
        return list(users_id)
