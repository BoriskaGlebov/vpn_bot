from aiogram.types import User as TgUser
from loguru import logger

from bot.users.adapter import UsersAPIAdapter
from shared.schemas.users import (
    SUser,
    SUserOut,
)


class UserService:
    """Сервис для управления пользователями.

    Отвечает за:
        - регистрацию пользователя;
        - получение и преобразование данных пользователя;
        - подготовку схем (DTO) для внешнего использования.
    """

    def __init__(self, adapter: UsersAPIAdapter) -> None:
        """Инициализирует сервис пользователей.

        Args:
            adapter: Адаптер для взаимодействия с Users API.

        """
        self.api_adapter = adapter

    async def register_or_get_user(
        self, telegram_user: TgUser
    ) -> tuple[SUserOut, bool]:
        """Регистрирует пользователя или возвращает существующего.

        Args:
            telegram_user: Объект пользователя Telegram.

        Returns
            Кортеж:
                - SUserOut: данные пользователя;
                - bool: флаг, указывающий, был ли пользователь создан.

        """
        logger.info(
            "Регистрация/получение пользователя telegram_id={}",
            telegram_user.id,
        )
        schema_user = SUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username or f"Гость_{telegram_user.id}",
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )

        user, is_new = await self.api_adapter.register(schema_user)
        if is_new:
            logger.success(
                "Создан новый пользователь telegram_id={} user_id={}",
                telegram_user.id,
                user.id,
            )
        else:
            logger.debug(
                "Получен существующий пользователь telegram_id={} user_id={}",
                telegram_user.id,
                user.id,
            )

        return user, is_new
