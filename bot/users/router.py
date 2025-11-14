from __future__ import annotations

from typing import Any

from aiogram import Bot, F
from aiogram.filters import (
    Command,
    CommandStart,
    StateFilter,
    and_f,
    or_f,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.keyboards.inline_kb import admin_main_kb, admin_user_control_kb
from bot.config import settings_bot
from bot.database import connection
from bot.redis_manager import SettingsRedis
from bot.users.keyboards.markup_kb import main_kb
from bot.users.services import UserService
from bot.utils.base_router import BaseRouter
from bot.utils.start_stop_bot import send_to_admins

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
    """Состояния FSM для начального меню бота.

    Attributes
        press_start (State): Состояние, когда пользователь нажал кнопку "Старт".
        press_admin (State): Состояние, когда пользователь нажал кнопку "Админ-панель".

    """

    press_start: State = State()
    press_admin: State = State()


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
        self.router.message.register(self.cmd_start, CommandStart())
        self.router.message.register(
            self.admin_start,
            or_f(Command("admin"), F.text.contains("⚙️ Панель администратора")),
        )

        self.router.message.register(
            self.mistake_handler_user,
            and_f(
                StateFilter(UserStates.press_admin),
                ~F.text.startswith("/"),
                ~F.text.in_(INVALID_FOR_ADMIN),
            ),
        )
        self.router.message.register(
            self.mistake_handler_user,
            and_f(
                StateFilter(UserStates.press_start),
                ~F.text.startswith("/"),
                ~F.text.in_(INVALID_FOR_USER),
            ),
        )

    @connection()
    @BaseRouter.log_method
    async def cmd_start(
        self,
        message: Message,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        """Обработчик команды /start.

        Проверяет, существует ли пользователь в базе данных.
        Если пользователь новый — добавляет его в БД, назначает роль User и формирует подписку.
        Отправляет приветственные сообщения и формирует клавиатуру главного меню.

        Args:
            message (Message): Сообщение Telegram, вызвавшее обработчик.
            session (AsyncSession): Асинхронная сессия БД (AsyncSession).
            state (FSMContext): Контекст FSM для работы с состояниями пользователя.

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.clear()
            user_info, is_new = await self.user_service.register_or_get_user(
                session=session, telegram_user=message.from_user
            )
            welcome_messages = m_start.get("welcome", {})
            if not is_new:
                self.logger.bind(
                    user=message.from_user.username or message.from_user.id
                ).info("Пользователь вернулся в бота")
                response_message = welcome_messages.get("again", [])[0].format(
                    username=message.from_user.full_name
                    or f"@{message.from_user.username}"
                    or f"Гость_{message.from_user.id}"
                )
                follow_up_message = welcome_messages.get("again", [])[1]

                await message.answer(
                    response_message, reply_markup=ReplyKeyboardRemove()
                )
                await message.answer(
                    follow_up_message,
                    reply_markup=main_kb(
                        active_subscription=user_info.subscription.is_active,
                        user_telegram_id=message.from_user.id,
                    ),
                )
            else:
                self.logger.bind(
                    user=message.from_user.username or message.from_user.id
                ).info(
                    f"Новый пользователь зарегистрирован: {message.from_user.id} ({message.from_user.username})"
                )
                response_message = welcome_messages.get("first", [])[0].format(
                    username=message.from_user.full_name
                    or f"@{message.from_user.username}"
                    or f"Гость_{message.from_user.id}"
                )
                follow_up_message = welcome_messages.get("first", [])[1]
                await message.answer(
                    response_message, reply_markup=ReplyKeyboardRemove()
                )
                await message.answer(
                    follow_up_message,
                    reply_markup=main_kb(
                        active_subscription=user_info.subscription.is_active,
                        user_telegram_id=message.from_user.id,
                    ),
                )
                if user_info.telegram_id not in settings_bot.ADMIN_IDS:
                    admin_message = m_admin.get("new_registration", "").format(
                        first_name=user_info.first_name or "undefined",
                        last_name=user_info.last_name or "undefined",
                        username=user_info.username or "undefined",
                        telegram_id=user_info.telegram_id,
                        roles=str(user_info.role),
                        subscription=str(user_info.subscription),
                    )
                    await send_to_admins(
                        bot=self.bot,
                        message_text=admin_message,
                        reply_markup=admin_user_control_kb(
                            filter_type=user_info.role.name,
                            telegram_id=message.from_user.id,
                        ),
                    )
            await state.set_state(UserStates.press_start)

    @BaseRouter.log_method
    async def admin_start(
        self, message: Message, state: FSMContext, **kwargs: Any
    ) -> None:
        """Обработчик команды /admin.

        Проверяет, является ли пользователь администратором.
        Если пользователь не админ — отправляет уведомление об отсутствии доступа.
        Если админ — очищает текущее состояние FSM, отправляет приветственное сообщение
        и переводит пользователя в состояние `press_admin`.

        Args:
            message (Message): Объект сообщения Telegram, который вызвал обработчик.
            state (FSMContext): Контекст конечного автомата для работы с состояниями пользователя.
            **kwargs (Any): Дополнительные аргументы (не используются напрямую, но могут быть переданы).

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.clear()

            if message.from_user.id not in settings_bot.ADMIN_IDS:
                self.logger.bind(
                    user=message.from_user.username or message.from_user.id
                ).warning(
                    f"Попытка доступа к админ-панели не админом: {message.from_user.id}"
                )
                await message.answer(
                    text=m_admin.get("off", "У вас нет доступа к этой команде!"),
                    reply_markup=ReplyKeyboardRemove(),
                )
                await self.bot.send_message(
                    text=m_error.get("admin_only", "У вас нет доступа к этой команде!"),
                    reply_markup=ReplyKeyboardRemove(),
                    chat_id=message.chat.id,
                )
                return
            self.logger.bind(
                user=message.from_user.username or message.from_user.id
            ).info(f"Админ {message.from_user.id} вошёл в панель администратора")
            await self.bot.send_message(
                chat_id=message.from_user.id,
                text=m_admin.get("on", [])[0],
                reply_markup=ReplyKeyboardRemove(),
            )
            await self.bot.send_message(
                chat_id=message.from_user.id,
                text=m_admin.get("on", [])[1],
                reply_markup=admin_main_kb(),
            )

            await state.set_state(UserStates.press_admin)
