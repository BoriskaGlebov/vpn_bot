import asyncio
from typing import Any

from admin.keyboards.inline_kb import admin_user_control_kb
from aiogram import F
from aiogram.dispatcher.router import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession
from utils.start_stop_bot import send_to_admins

from bot.config import bot, logger, settings_bot
from bot.database import connection
from bot.users.dao import UserDAO
from bot.users.keyboards.markup_kb import main_kb
from bot.users.schemas import SRole, SUser, SUserTelegramID

m_admin = settings_bot.MESSAGES["modes"]["admin"]
m_start = settings_bot.MESSAGES["modes"]["start"]
m_error = settings_bot.MESSAGES["errors"]
m_echo = settings_bot.MESSAGES["general"]["echo"]

user_router = Router()


class UserStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для начального меню бота.

    Attributes
        press_start (State): Состояние, когда пользователь нажал кнопку "Старт".
        press_admin (State): Состояние, когда пользователь нажал кнопку "Админ-панель".

    """

    press_start: State = State()
    press_admin: State = State()


@user_router.message(CommandStart())  # type: ignore[misc]
@connection()
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
    **kwargs: Any,
) -> None:
    """Обработчик команды /start.

    Проверяет, существует ли пользователь в базе данных.
    Если пользователь новый — добавляет его в БД, назначает роль User и формирует подписку.
    Отправляет приветственные сообщения и формирует клавиатуру главного меню.

    Args:
        message (Message): Сообщение Telegram, вызвавшее обработчик.
        command (CommandObject): Объект команды Telegram.
        session (Any): Асинхронная сессия БД (AsyncSession).
        state (FSMContext): Контекст FSM для работы с состояниями пользователя.
        **kwargs (Any): Дополнительные аргументы.

    Returns
        None

    """
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        schema_telegram_id = SUserTelegramID(telegram_id=message.chat.id)
        await state.clear()
        user_info = await UserDAO.find_one_or_none(
            session=session, filters=schema_telegram_id
        )
        welcome_messages = m_start["welcome"]
        if user_info:
            response_message = welcome_messages["again"][0].format(
                username=message.from_user.full_name
                or message.from_user.username
                or "Гость"
            )
            follow_up_message = welcome_messages["again"][1]

            await message.answer(response_message, reply_markup=ReplyKeyboardRemove())
            await message.answer(
                follow_up_message,
                reply_markup=main_kb(
                    active_subscription=user_info.subscription.is_active,
                    user_telegram_id=message.from_user.id,
                ),
            )
        else:
            schema_user = SUser(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            if schema_user.telegram_id in settings_bot.ADMIN_IDS:
                schema_role = SRole(name="admin")
            else:
                schema_role = SRole(name="user")
            new_user = await UserDAO.add_role_subscription(
                session=session, values_user=schema_user, values_role=schema_role
            )
            response_message = welcome_messages["first"][0].format(
                username=message.from_user.full_name
                or message.from_user.username
                or "Гость"
            )
            follow_up_message = welcome_messages["first"][1]
            await message.answer(response_message, reply_markup=ReplyKeyboardRemove())
            await message.answer(
                follow_up_message,
                reply_markup=main_kb(
                    active_subscription=new_user.subscription.is_active,
                    user_telegram_id=message.from_user.id,
                ),
            )
            if schema_user.telegram_id not in settings_bot.ADMIN_IDS:
                admin_message = m_admin["new_registration"].format(
                    first_name=new_user.first_name or "—",
                    last_name=new_user.last_name or "",
                    username=new_user.username or "—",
                    telegram_id=new_user.telegram_id,
                    roles=", ".join(role.name for role in new_user.roles),
                    subscription=str(new_user.subscription),
                )
                await send_to_admins(
                    bot=bot,
                    message_text=admin_message,
                    reply_markup=admin_user_control_kb(message.from_user.id),
                )
        await state.set_state(UserStates.press_start)


@user_router.message(Command("admin"))  # type: ignore[misc]
async def admin_start(
    message: Message, session: AsyncSession, state: FSMContext, **kwargs: Any
) -> None:
    """Обработчик команды /admin.

    Проверяет, является ли пользователь администратором.
    Если пользователь не админ — отправляет уведомление об отсутствии доступа.
    Если админ — очищает текущее состояние FSM, отправляет приветственное сообщение
    и переводит пользователя в состояние `press_admin`.

    Args:
        message (Message): Объект сообщения Telegram, который вызвал обработчик.
        session (AsyncSession): Асинхронная сессия базы данных.
        state (FSMContext): Контекст конечного автомата для работы с состояниями пользователя.
        **kwargs (Any): Дополнительные аргументы (не используются напрямую, но могут быть переданы).

    Returns
        None

    """
    await state.clear()

    if message.from_user.id not in settings_bot.ADMIN_IDS:
        await message.answer(
            text=m_admin.get("off", "У вас нет доступа к этой команде!"),
            reply_markup=ReplyKeyboardRemove(),
        )
        await bot.send_message(
            text=m_error.get("admin_only", "У вас нет доступа к этой команде!"),
            reply_markup=ReplyKeyboardRemove(),
            chat_id=message.chat.id,
        )
        return

    await bot.send_message(
        chat_id=message.from_user.id,
        text=m_admin.get("on", "Кажись не придумал сюда сообщение!"),
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.set_state(UserStates.press_admin)


@user_router.message(
    UserStates.press_admin,
    ~F.text.startswith("/")
    & ~(
        F.text.contains("⚙️ Админ-панель") | F.text.contains("❓ Помощь в настройке VPN")
    ),
)  # type: ignore[misc]
@user_router.message(
    UserStates.press_start,
    ~F.text.startswith("/")
    & ~(
        F.text.contains("🔑 Получить VPN-конфиг AmneziaVPN")
        | F.text.contains("🌐 Получить VPN-конфиг AmneziaWG")
        | F.text.contains("📈 Проверить статус подписки")
        | F.text.contains("❓ Помощь в настройке VPN")
        | F.text.contains("💰 Выбрать подписку VPN-Boriska")
    ),
)  # type: ignore[misc]
async def mistake_handler_user(message: Message, state: FSMContext) -> None:
    """Обработчик некорректных сообщений от пользователя.

    Если пользователь вводит текст вместо кнопок, сообщение удаляется,
    и бот напоминает, что нужно использовать кнопки.

    Args:
        message (Message): Сообщение пользователя
        state (FSMContext): Текущее состояние пользователя

    Returns
        None

    """
    try:
        await asyncio.sleep(2)
        await message.delete()
    except Exception as e:
        logger.error(e)
        pass

    current_state = await state.get_state()
    state_me = current_state.split(":")[1] if current_state else None
    if state_me == "press_start":
        answer_text = m_error["unknown_command"]
    else:
        answer_text = m_error["unknown_command_admin"]
    await message.answer(text=answer_text)
