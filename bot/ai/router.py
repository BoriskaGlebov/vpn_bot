from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import (
    Command,
)
from aiogram.types import Message
from loguru._logger import Logger

from bot.ai.services.chat.service import ChatService
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
        chat_service: ChatService,
    ) -> None:
        super().__init__(bot, logger)
        self.redis_manager = redis_manager
        self.chat_service = chat_service

    def _register_handlers(self) -> None:
        self.router.message.register(self.ai_start, Command("ai"))
        self.router.message.register(self.ai_questions, F.text)

    @BaseRouter.log_method
    async def ai_start(
        self,
        message: Message,
    ) -> None:
        """ДОки потом."""
        await message.answer("Функции ИИ")
        await message.answer("Сюда можно написать вопросы для ИИ бота")

    @BaseRouter.log_method
    async def ai_questions(self, message: Message) -> None:
        answer = await self.chat_service.ask(message.text)
        await message.answer(answer)
