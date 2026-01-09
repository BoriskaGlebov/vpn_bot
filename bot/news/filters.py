from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.config import settings_bot


class IsAdmin(BaseFilter):
    """Фильтр для проверки прав администратора.

    Фильтр пропускает только те события (Message или CallbackQuery),
    которые были инициированы пользователем, чей Telegram ID
    присутствует в списке администраторов `settings_bot.admin_ids`.

    Используется для ограничения доступа к административным
    командам и действиям бота.
    """

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Проверяет, является ли пользователь администратором.

        Args:
            event (Message | CallbackQuery): Событие от пользователя.

        Returns
            bool: True, если пользователь является администратором,
            иначе False.

        """
        user = event.from_user
        if user is None:
            return False

        return user.id in settings_bot.admin_ids
