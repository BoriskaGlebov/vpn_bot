from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.redis_manager import SettingsRedis
from bot.users.schemas import SUserOut


class UserService:
    """Сервис для управления пользователями.

    Отвечает за регистрацию и получение данных пользователя, а также за
    взаимодействие с Redis для хранения вспомогательных данных.

    """

    def __init__(self, redis: SettingsRedis) -> None:
        """Инициализация сервиса пользователей.

        Args:
            redis (SettingsRedis): Менеджер работы с Redis для хранения настроек и состояния.

        """
        self.redis = redis

    async def register_or_get_user(
        self, session: AsyncSession, telegram_user: TgUser
    ) -> tuple[SUserOut, bool]:
        pass
