from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from aiogram.types import Message
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.redis_manager import SettingsRedis
from bot.users.services import UserService
from bot.utils.base_router import BaseRouter

m_admin = settings_bot.MESSAGES.get("modes", {}).get("admin", {})
m_start = settings_bot.MESSAGES.get("modes", {}).get("start", {})
m_error = settings_bot.MESSAGES.get("errors", {})
m_echo = settings_bot.MESSAGES.get("general", {}).get("echo", {})
INVALID_FOR_USER = [
    "💰 Выбрать подписку VPN-Boriska",
    "🔑 Получить VPN-конфиг AmneziaVPN",
    "🌐 Получить VPN-конфиг AmneziaWG",
    "📈 Проверить статус подписки",
    "❓ Помощь в настройке VPN",
    "💰 Выбрать подписку VPN-Boriska",
    "💎 Продлить VPN-Boriska",
]
INVALID_FOR_ADMIN = [
    "⚙️ Админ-панель",
    "❓ Помощь в настройке VPN",
]


class UserStates(StatesGroup):  # type: ignore[misc]
    pass


class UserRouter(BaseRouter):
    """Роутер для обработки пользовательских команд и сообщений.

    Этот класс отвечает за регистрацию и обработку всех пользовательских хендлеров:
    команд `/start`, `/admin`, а также сообщений, не соответствующих ожидаемому
    состоянию пользователя. Использует `redis_manager` для взаимодействия с Redis-хранилищем.

    Attributes
        bot (Bot): Экземпляр бота Telegram.
        router (Router): Экземпляр роутера aiogram для регистрации хендлеров.
        logger (Logger): Экземпляр логгера loguru.
        redis_manager (SettingsRedis): Менеджер для работы с Redis (сохранение и получение данных).
        user_service (UserService): Бизнес логика пользователя.

    """

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        redis_manager: SettingsRedis,
        user_service: UserService,
    ) -> None:
        super().__init__(bot, logger)
        self.redis_manager = redis_manager
        self.user_service = user_service

    def _register_handlers(self) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def cmd_start(
        self,
        message: Message,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        pass

    @BaseRouter.log_method
    async def admin_start(
        self, message: Message, state: FSMContext, **kwargs: Any
    ) -> None:
        pass
