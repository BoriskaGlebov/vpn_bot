from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession
from users.schemas import SUserOut

from bot.config import settings_bot
from bot.redis_manager import SettingsRedis
from bot.users.dao import UserDAO
from bot.users.schemas import SRole, SUser, SUserTelegramID


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
        """Регистрирует пользователя, если он отсутствует, или возвращает существующего.

        Если пользователь с данным Telegram ID отсутствует в базе данных, создаётся новая
        запись, а также автоматически назначается роль:
        - "admin" — если Telegram ID находится в списке `settings_bot.ADMIN_IDS`
        - "user" — для всех остальных пользователей

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy для работы с БД.
            telegram_user (TgUser): Объект пользователя из Telegram (aiogram.types.User).

        Returns
            tuple[SUserOut, bool]: Кортеж из:
                - экземпляра схемы `SUserOut`
                - булевого флага:
                    - `True`, если пользователь был создан;
                    - `False`, если пользователь уже существовал.

        """
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=telegram_user.id),
        )
        if not user:
            schema_user = SUser(
                telegram_id=telegram_user.id,
                username=telegram_user.username or f"Гость_{telegram_user.id}",
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
            schema_role = SRole(
                name="admin" if telegram_user.id in settings_bot.ADMIN_IDS else "user"
            )
            user = await UserDAO.add_role_subscription(
                session=session,
                values_user=schema_user,
                values_role=schema_role,
            )
            return SUserOut.model_validate(user), True
        return SUserOut.model_validate(user), False
