from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings_api
from api.core.mapper.user_mapper import UserMapper
from api.users.dao import UserDAO
from api.users.schemas import (
    SRole,
    SUser,
    SUserOut,
    SUserTelegramID,
)


class UserService:
    """Сервис для управления пользователями.

    Отвечает за регистрацию и получение данных пользователя.
    """

    async def register_or_get_user(
        self, session: AsyncSession, telegram_user: SUser
    ) -> tuple[SUserOut, bool]:
        """Регистрирует пользователя, если он отсутствует, или возвращает существующего.

        Если пользователь с данным Telegram ID отсутствует в базе данных, создаётся новая
        запись, а также автоматически назначается роль:
        - "admin" — если Telegram ID находится в списке `settings_bot.ADMIN_IDS`
        - "user" — для всех остальных пользователей

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy для работы с БД.
            telegram_user (SUser): Схема с данными из телеграм пользователя.

        Returns
            tuple[SUserOut, bool]: Кортеж из:
                - экземпляра схемы `SUserOut`
                - булевого флага:
                    - `True`, если пользователь был создан;
                    - `False`, если пользователь уже существовал.

        """
        logger.debug("Начало обработки пользователя")
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=telegram_user.telegram_id),
        )
        if user:
            logger.info("Пользователь найден в базе")
            return await UserMapper.to_schema(user), False
        logger.info("Пользователь не найден, создаём нового")
        schema_user = SUser(
            telegram_id=telegram_user.telegram_id,
            username=telegram_user.username or f"Гость_{telegram_user.telegram_id}",
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )
        schema_role = SRole(
            name=(
                "admin"
                if telegram_user.telegram_id in settings_api.admin_ids
                else "user"
            )
        )
        logger.debug(f"Назначается роль: {schema_role}")
        user = await UserDAO.add_role_subscription(
            session=session,
            values_user=schema_user,
            values_role=schema_role,
        )
        logger.success("Пользователь успешно создан")
        return await UserMapper.to_schema(user), True
