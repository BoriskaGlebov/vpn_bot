import asyncio
from typing import Any

from aiogram import Bot, F
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, StateFilter, and_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.news.keyboards.inline_kb import NewsAction, NewsCB, news_confirm_kb
from bot.news.services import NewsService
from bot.utils.base_router import BaseRouter

m_news = settings_bot.messages.modes.news


class NewStates(StatesGroup):  # type: ignore[misc]
    """FSM состояния для создания и отправки новости.

    Attributes
        news_start (State): Состояние ожидания текста или фото новости.
        confirm_news (State): Состояние подтверждения рассылки новости.

    """

    news_start: State = State()
    confirm_news: State = State()


class NewsRouter(BaseRouter):
    """Маршрутизатор для работы с новостной рассылкой.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        logger (Logger): Логгер Loguru.
        news_service (NewsService): Сервис для работы с новостями и получателями.

    """

    def __init__(self, bot: Bot, logger: Logger, news_service: NewsService) -> None:
        super().__init__(bot, logger)
        self.news_service = news_service

    def _register_handlers(self) -> None:
        self.router.message.register(self.start_handler, Command("news"))
        self.router.message.register(
            self.news_text_handler, StateFilter(NewStates.news_start)
        )
        self.router.callback_query.register(
            self.confirm_news_handler,
            and_f(
                StateFilter(NewStates.confirm_news),
                NewsCB.filter(F.action == NewsAction.CONFIRM),
            ),
        )
        self.router.callback_query.register(
            self.cancel_news_handler,
            and_f(
                StateFilter(NewStates.confirm_news),
                NewsCB.filter(F.action == NewsAction.CANCEL),
            ),
        )

    @BaseRouter.log_method
    async def start_handler(self, message: Message, state: FSMContext) -> None:
        """Обработчик команды /news: начинает процесс создания новости.

        Args:
            message (Message): Сообщение пользователя.
            state (FSMContext): Контекст FSM для хранения состояния.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(text=m_news.start, reply_markup=ReplyKeyboardRemove())
            await state.set_state(NewStates.news_start)

    @BaseRouter.log_method
    async def news_text_handler(
        self,
        message: Message,
        state: FSMContext,
    ) -> None:
        """Обработчик текста или фото новости, сохраняет данные в FSMContext и отправляет предпросмотр.

        Args:
            message (Message): Сообщение с текстом или фото.
            state (FSMContext): Контекст FSM.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            data: dict[str, Any] = {}
            if message.text:
                data["content_type"] = "text"
                data["text"] = message.text
                await message.answer(
                    text=(
                        "📰 Вот как будет выглядеть новость:\n\n"
                        f"{data['text']}\n\n"
                        "Отправляем?"
                    ),
                    reply_markup=news_confirm_kb(),
                )
            elif message.photo:
                data["content_type"] = "photo"
                data["photo_file_id"] = message.photo[-1].file_id
                data["caption"] = message.caption or ""
                await message.answer_photo(
                    photo=data["photo_file_id"],
                    caption=(
                        "📰 Вот как будет выглядеть новость:\n\n"
                        f"{data['caption']}\n\n"
                        "Отправляем?"
                    ),
                    reply_markup=news_confirm_kb(),
                )
            else:
                await message.answer(
                    "✍️ Отправь текст или картинку с подписью для новости."
                )
                return
            await state.update_data(news=data)
            await state.set_state(NewStates.confirm_news)

    @BaseRouter.log_method
    @connection()
    @BaseRouter.require_message
    async def confirm_news_handler(
        self,
        query: CallbackQuery,
        msg: Message,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        """Обработчик подтверждения рассылки новости.

        Отправляет новость всем пользователям, кроме админов, учитывает FloodWait,
        ForbiddenError и другие ошибки Telegram API.

        Args:
            query (CallbackQuery): Колбек подтверждения новости.
            msg (Message): Сообщение предпросмотра новости.
            session (AsyncSession): Асинхронная сессия базы данных.
            state (FSMContext): FSMContext с сохранёнными данными новости.

        """
        await query.answer("Отправляем!")
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            data = await state.get_data()
            news: dict[str, Any] = data["news"]

            recipients = await self.news_service.all_users_id(session=session)
            sent = 0

            for user_id in recipients:
                try:
                    if news["content_type"] == "text":
                        await self.bot.send_message(user_id, news["text"])
                    elif news["content_type"] == "photo":
                        await self.bot.send_photo(
                            user_id,
                            photo=news["photo_file_id"],
                            caption=news["caption"],
                        )
                    sent += 1

                except TelegramRetryAfter as e:
                    self.logger.warning(
                        f"FloodWait {e.retry_after}s для {user_id}, жду..."
                    )
                    await asyncio.sleep(e.retry_after)
                    try:
                        if news["content_type"] == "text":
                            await self.bot.send_message(user_id, news["text"])
                        elif news["content_type"] == "photo":
                            await self.bot.send_photo(
                                user_id,
                                photo=news["photo_file_id"],
                                caption=news["caption"],
                            )
                        sent += 1
                    except Exception as exc:
                        self.logger.error(
                            f"Повторная отправка не удалась {user_id}: {exc}"
                        )

                except TelegramForbiddenError:
                    self.logger.warning(
                        f"Пользователь {user_id} заблокировал бота, пропускаем."
                    )

                except TelegramBadRequest as e:
                    self.logger.warning(f"Ошибка TelegramBadRequest для {user_id}: {e}")

                except Exception as exc:
                    self.logger.error(
                        f"Неизвестная ошибка при отправке {user_id}: {exc}"
                    )

                await asyncio.sleep(0.05)

            if msg.photo:
                await self.bot.edit_message_caption(
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    caption=f"✅ Новость отправлена.\nПолучателей: {sent}",
                )
            else:
                await self.bot.edit_message_text(
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    text=f"✅ Новость отправлена.\nПолучателей: {sent}",
                )

            await state.clear()

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def cancel_news_handler(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
    ) -> None:
        """Обработчик отмены рассылки новости.

        Args:
            query (CallbackQuery): Колбек отмены.
            msg (Message): Сообщение предпросмотра новости.
            state (FSMContext): FSMContext для очистки состояния.

        """
        await query.answer(text="Отменил")
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            await msg.edit_text("❌ Рассылка отменена.")
            await state.clear()
