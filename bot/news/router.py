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

from bot.core.config import settings_bot
from bot.core.filters import IsAdmin
from bot.news.keyboards.inline_kb import NewsAction, NewsCB, news_confirm_kb
from bot.news.services import NewsService
from bot.utils.base_router import BaseRouter
from bot.utils.start_stop_bot import send_to_admins

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
        is_admin = IsAdmin()
        self.router.message.register(
            self.start_handler, and_f(Command("news"), is_admin)
        )
        self.router.message.register(
            self.news_text_handler, and_f(StateFilter(NewStates.news_start), is_admin)
        )
        self.router.callback_query.register(
            self.confirm_news_handler,
            and_f(
                StateFilter(NewStates.confirm_news),
                NewsCB.filter(F.action == NewsAction.CONFIRM),
                is_admin,
            ),
        )
        self.router.callback_query.register(
            self.cancel_news_handler,
            and_f(
                StateFilter(NewStates.confirm_news),
                NewsCB.filter(F.action == NewsAction.CANCEL),
                is_admin,
            ),
        )
        (
            self.router.message.register(
                self.mistake_handler_user,
                and_f(StateFilter(NewStates.confirm_news), F.text, is_admin),
            ),
        )

    async def _send_news(self, user_id: int, news_data: dict[str, Any]) -> None:
        """Фунция расслыки новостей."""
        if news_data["content_type"] == "text":
            await self.bot.send_message(user_id, news_data["text"])

        elif news_data["content_type"] == "photo":
            await self.bot.send_photo(
                user_id,
                photo=news_data["photo_file_id"],
                caption=news_data["caption"],
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
    @BaseRouter.require_message
    async def confirm_news_handler(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
    ) -> None:
        """Обработчик подтверждения рассылки новости.

        Отправляет новость всем пользователям, кроме админов, учитывает FloodWait,
        ForbiddenError и другие ошибки Telegram API.

        Args:
            query (CallbackQuery): Колбек подтверждения новости.
            msg (Message): Сообщение предпросмотра новости.
            state (FSMContext): FSMContext с сохранёнными данными новости.

        """
        await query.answer("Отправляем!")
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            data = await state.get_data()
            news = data.get("news")
            if not news or "content_type" not in news:
                self.logger.warning(
                    f"Данные новости отсутствуют или повреждены для пользователя {query.from_user.id}"
                )
                await msg.edit_text(
                    "❌ Не удалось получить данные новости. Попробуйте снова."
                )
                await state.clear()
                await query.answer()
                return
            recipients = await self.news_service.all_users_id()
            sent = 0
            self.logger.bind(user=query.from_user.username or "undefined").info(
                f"Начата рассылка новостей "
                f"({query.from_user.id}), тип новости: {news['content_type']}"
            )
            for user_id in recipients:
                try:
                    await self._send_news(user_id, news)
                    sent += 1

                except TelegramRetryAfter as e:
                    self.logger.warning(
                        f"FloodWait {e.retry_after}s для {user_id}, жду..."
                    )
                    await asyncio.sleep(e.retry_after)
                    try:
                        await self._send_news(user_id, news)
                        sent += 1
                    except Exception as exc:
                        self.logger.error(
                            f"Повторная отправка не удалась {user_id}: {exc}"
                        )

                except TelegramForbiddenError:
                    self.logger.warning(
                        f"Пользователь {user_id} заблокировал бота, пропускаем."
                    )
                    await send_to_admins(
                        bot=self.bot,
                        message_text=f"Пользователь {user_id} "
                        f"заблокировал бота, пропускаем.",
                    )

                except TelegramBadRequest as e:
                    self.logger.warning(f"Ошибка TelegramBadRequest для {user_id}: {e}")
                    await send_to_admins(
                        bot=self.bot,
                        message_text=f"Ошибка TelegramBadRequest для {user_id}: {e}",
                    )
                except Exception as exc:
                    self.logger.error(
                        f"Неизвестная ошибка при отправке {user_id}: {exc}"
                    )
                    await send_to_admins(
                        bot=self.bot,
                        message_text=f"Неизвестная ошибка при отправке {user_id}: {exc}",
                    )

                await asyncio.sleep(0.05)
            self.logger.info(f"Рассылка завершена. Отправлено сообщений: {sent}")
            await state.clear()
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
            if hasattr(msg, "photo") and msg.photo:
                await self.bot.edit_message_caption(
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    caption="❌ Рассылка отменена.",
                )
            else:
                await self.bot.edit_message_text(
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    text="❌ Рассылка отменена.",
                )
            await state.clear()
        self.logger.bind(user=query.from_user.username).info(
            f"Рассылка отменена ({query.from_user.id})"
        )
