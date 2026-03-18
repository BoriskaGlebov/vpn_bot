from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import (
    Command,
)
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.services.service import ChatService
from bot.config import settings_bot
from bot.database import connection
from bot.redis_manager import RedisClient
from bot.utils.base_router import BaseRouter

m_ai = settings_bot.messages.modes.ai_assistant


class AIRouter(BaseRouter):
    """Роутер для работы с ИИ-ассистентом Telegram.

    Обрабатывает команды /ai_assistant и текстовые сообщения,
    пересылает их в `ChatService`, хранит историю пользователя
    в FSMContext и отвечает с учетом этой истории.
    """

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        redis_manager: RedisClient,
        chat_service: ChatService,
    ) -> None:
        """Инициализация AIRouter.

        Args:
            bot (Bot): Объект бота Aiogram.
            logger (Logger): Логгер Loguru.
            redis_manager (RedisClient): Менеджер настроек Redis.
            chat_service (ChatService): Сервис для общения с LLM.

        """
        super().__init__(bot, logger)
        self.redis_manager = redis_manager
        self.chat_service = chat_service

    def _register_handlers(self) -> None:
        """Регистрация обработчиков сообщений."""
        self.router.message.register(self.ai_start, Command("ai_assistant"))
        self.router.message.register(self.ai_questions, F.text)

    @BaseRouter.log_method
    async def ai_start(self, message: Message, state: FSMContext) -> None:
        """Обработка команды /ai_assistant.

        Очищает состояние пользователя и выводит приветственное сообщение.

        Args:
            message (Message): Объект сообщения пользователя.
            state (FSMContext): Контекст FSM для пользователя.

        """
        await state.clear()
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(
                text=m_ai.start,
                reply_markup=ReplyKeyboardRemove(),
            )

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_user
    async def ai_questions(
        self, message: Message, user: TgUser, session: AsyncSession, state: FSMContext
    ) -> None:
        """Обработка текстового сообщения от пользователя.

        1. Проверяет минимальную длину вопроса.
        2. Обновляет историю последних 5 сообщений пользователя в FSMContext.
        3. Передает вопрос и историю в ChatService для генерации ответа.
        4. Отправляет ответ пользователю и логирует события.

        Args
            message (Message): Объект сообщения пользователя.
            user (TgUser): Информация о пользователе Telegram.
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            state (FSMContext): FSMContext для хранения истории сообщений.

        Notes
            - История пользователя ограничена последними 5 сообщениями.
            - Логирование ведется с привязкой к username или id пользователя.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            text = message.text or ""
            if len(text.split()) < 3:
                await message.answer(text=m_ai.short_question)
                return
            user_logger = self.logger.bind(user=user.username or user.id or "undefined")
            # history = await state.get_data()
            # conversation: list[str] = history.get("conversation", [])
            #
            # conversation.append(text)
            # conversation = conversation[-5:]
            # await state.update_data(conversation=conversation)

            # user_logger.info(
            #     "Пользователь {}: история сообщений ({}): {}",
            #     user.id,
            #     len(conversation),
            #     conversation,
            # )

            answer = await self.chat_service.ask(question=text)

            await message.answer(answer)
            user_logger.info(
                "Ответ пользователю {} отправлен ({} символов)",
                user.id,
                len(answer),
            )
