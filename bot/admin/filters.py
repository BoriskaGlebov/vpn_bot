from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.config import settings_bot


class IsAdminFilter(BaseFilter):
    """Фильтр, разрешающий обработку событий только администраторам бота.

    Фильтр проверяет наличие отправителя события и то, что его Telegram ID
    присутствует в списке идентификаторов администраторов, заданных
    в настройках бота.

    Поддерживает обработку как сообщений, так и callback-запросов.
    """

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Проверяет, обладает ли отправитель события правами администратора.

        Args:
            event: Входящее событие Telegram — сообщение или callback-запрос.

        Returns
            True, если пользователь является администратором бота,
            иначе False.

        """
        user = event.from_user
        if user is None:
            return False

        return user.id in settings_bot.admin_ids
