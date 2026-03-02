from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import (
    Command,
)
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.services.chat.service import ChatService
from bot.database import connection
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
    async def ai_start(self, message: Message, state: FSMContext) -> None:
        """ДОки потом."""
        await state.clear()
        await message.answer("Функции ИИ")
        await message.answer(
            "Сюда можно написать вопросы для ИИ бота",
            reply_markup=ReplyKeyboardRemove(),
        )

    @connection()
    @BaseRouter.log_method
    async def ai_questions(self, message: Message, session: AsyncSession) -> None:
        answer = await self.chat_service.ask(message.text, session=session)
        await message.answer(answer)
