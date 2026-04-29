from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.core.config import settings_bot
from bot.subscription.enums import ToggleSubscriptionMode
from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUser


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


class IsPremium(BaseFilter):
    """Проверяет, что у пользователя есть активная premium-подписка.

    Фильтр:
        - регистрирует пользователя (если он отсутствует в БД)
        - проверяет тип подписки (PREMIUM)
        - проверяет, что подписка активна

    Args:
        event (Message | CallbackQuery): входящее событие Telegram.

    Returns
        bool: True, если у пользователя активная premium-подписка,
        иначе False.

    """

    def __init__(self, user_adapter: UsersAPIAdapter) -> None:
        super().__init__()
        self.user_adapter = user_adapter

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Проверяет, что у пользователя есть активная premium-подписка."""
        user = event.from_user
        if user is None:
            return False
        suser = SUser(telegram_id=user.id)
        user_db, _ = await self.user_adapter.register(user=suser)
        if user_db is None:
            return False
        if user_db.current_subscription is None:
            return False
        is_premium = user_db.current_subscription.type == ToggleSubscriptionMode.PREMIUM
        is_active = user_db.current_subscription.is_active

        return is_premium and is_active
