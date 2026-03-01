from __future__ import annotations

from aiogram import Bot
from aiogram.filters import (
    Command,
)
from aiogram.types import Message
from loguru._logger import Logger

from bot.redis_manager import SettingsRedis
from bot.utils.base_router import BaseRouter


# TODO докстринг и все такое
class AIRouter(BaseRouter):
    """Ротер с работой ИИ."""

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        redis_manager: SettingsRedis,
    ) -> None:
        super().__init__(bot, logger)
        self.redis_manager = redis_manager

    def _register_handlers(self) -> None:
        self.router.message.register(self.ai_start, Command("ai"))

    @BaseRouter.log_method
    async def ai_start(
        self,
        message: Message,
    ) -> None:
        """ДОки потом."""
        await message.answer("Функции ИИ")
