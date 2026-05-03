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
from aiogram.types import User as TGUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.core.config import settings_bot
from bot.core.filters import IsAdmin
from bot.news.keyboards.inline_kb import (
    NewsAction,
    NewsCB,
    TargetAction,
    TargetCB,
    news_confirm_kb,
    target_choice_kb,
)
from bot.news.services import NewsService
from bot.utils.base_router import BaseRouter
from bot.utils.start_stop_bot import send_to_admins

m_news = settings_bot.messages.modes.news


class NewStates(StatesGroup):  # type: ignore[misc]
    """FSM состояния для создания и отправки новости.

    Attributes
        news_start (State): Состояние ожидания текста или фото новости.
        choose_target (State): Способ рассылки массово/по id.
        wait_user_id (State): Ожидается ввод ID
        confirm_news (State): Состояние подтверждения рассылки новости.

    """

    news_start: State = State()
    choose_target: State = State()
    wait_user_id: State = State()
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
            self.choose_target_handler,
            and_f(
                StateFilter(NewStates.choose_target),
                TargetCB.filter(),
                is_admin,
            ),
        )
        self.router.message.register(
            self.user_id_handler,
            and_f(
                StateFilter(NewStates.wait_user_id),
                is_admin,
            ),
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
        elif news_data["content_type"] == "video":
            await self.bot.send_video(
                user_id,
                video=news_data["video_file_id"],
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
            elif message.photo:
                data["content_type"] = "photo"
                data["photo_file_id"] = message.photo[-1].file_id
                data["caption"] = message.caption or ""
            elif message.video:
                data["content_type"] = "video"
                data["video_file_id"] = message.video.file_id
                data["caption"] = message.caption or ""

            else:
                await message.answer(
                    "✍️ Отправь текст или картинку с подписью для новости."
                )
                return
            await state.update_data(news=data)
            await state.set_state(NewStates.choose_target)
            await message.answer(
                "Куда отправляем?",
                reply_markup=target_choice_kb(),  # сделаешь 2 кнопки
            )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def choose_target_handler(
        self,
        query: CallbackQuery,
        message: Message,
        callback_data: TargetCB,
        state: FSMContext,
    ) -> None:
        """Обрабатывает выбор типа рассылки (всем или одному пользователю).

        Args:
            query: CallbackQuery от нажатия кнопки.
            message: Сообщение, к которому привязан callback.
            callback_data: Распарсенные данные callback (TargetCB).
            state: Контекст FSM.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await query.answer()

            if callback_data.target == TargetAction.ALL:
                await state.update_data(target="all")
                await self._show_preview(message, state)

            elif callback_data.target == TargetAction.ONE:
                await state.set_state(NewStates.wait_user_id)
                await message.answer("Введи user_id:")

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def user_id_handler(
        self, message: Message, user: TGUser, state: FSMContext
    ) -> None:
        """Обрабатывает ввод user_id для персональной отправки.

        Args:
            message: Сообщение с введённым user_id.
            user: Telegram пользователь (инжектится декоратором).
            state: Контекст FSM.

        """
        try:
            user_id = int(message.text)
        except ValueError:
            await message.answer("Некорректный user_id")
            return

        await state.update_data(target="one", user_id=user_id)
        await self._show_preview(message, state)

    async def _show_preview(self, msg: Message, state: FSMContext) -> None:
        """Отображает предпросмотр новости перед отправкой.

        Args:
            msg: Сообщение, в которое отправляется предпросмотр.
            state: Контекст FSM с сохранёнными данными новости.

        """
        data = await state.get_data()
        news = data["news"]

        if news["content_type"] == "text":
            await msg.answer(
                f"📰 Предпросмотр:\n\n{news['text']}\n\nОтправляем?",
                reply_markup=news_confirm_kb(),
            )
        elif news["content_type"] == "photo":
            await msg.answer_photo(
                photo=news["photo_file_id"],
                caption=f"📰 Предпросмотр:\n\n{news['caption']}\n\nОтправляем?",
                reply_markup=news_confirm_kb(),
            )
        elif news["content_type"] == "video":
            await msg.answer_video(
                video=news["video_file_id"],
                caption=f"📰 Предпросмотр:\n\n{news['caption']}\n\nОтправляем?",
                reply_markup=news_confirm_kb(),
            )

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
            target = data.get("target")
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
            sent = 0
            if target == "one":
                user_id = data.get("user_id")
                try:
                    await self._send_news(user_id, news)
                    sent = 1
                except Exception as e:
                    sent = 0
                    self.logger.error(f"Ошибка отправки {user_id}: {e}")

            elif target == "all":
                recipients = await self.news_service.all_users_id()

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
                        self.logger.warning(
                            f"Ошибка TelegramBadRequest для {user_id}: {e}"
                        )
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
            elif msg.video:
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
