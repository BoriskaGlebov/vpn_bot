from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Message, ReplyKeyboardRemove, User
from config import settings_bot

from bot.users.router import StartCommand, admin_start, cmd_start, m_error


@pytest.mark.asyncio
@patch("bot.users.router.UserDAO")
@patch("bot.users.router.RoleDAO")
@patch("bot.users.router.ChatActionSender")
async def test_cmd_start_new_user(
    mock_chat_action, mock_role_dao, mock_user_dao, fake_message, session, fake_state
):
    """Тест: новый пользователь впервые пишет /start."""
    # Настраиваем поведение DAO
    mock_user_dao.find_one_or_none = AsyncMock(return_value=None)
    mock_user_dao.add = AsyncMock()
    mock_user_dao.add_role = AsyncMock()
    mock_role_dao.find_one_or_none = AsyncMock()

    # Подменяем тексты сообщений
    from bot.config import settings_bot

    settings_bot.MESSAGES = {
        "modes": {
            "start": {
                "welcome": {
                    "first": ["Привет, {username}!", "Добро пожаловать!"],
                    "again": ["Снова привет, {username}!", "Рады видеть!"],
                }
            },
            "admin": {},
        },
        "errors": {},
    }
    settings_bot.ADMIN_IDS = [9999]  # текущий пользователь не админ

    await cmd_start(message=fake_message, command=None, state=fake_state)

    # Проверки
    mock_user_dao.find_one_or_none.assert_awaited_once()
    mock_user_dao.add.assert_awaited_once()
    mock_user_dao.add_role.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(StartCommand.press_start)
    assert fake_message.answer.await_count == 2


@pytest.mark.asyncio
@patch("bot.users.router.UserDAO")
@patch("bot.users.router.ChatActionSender")
async def test_cmd_start_existing_user(
    mock_chat_action, mock_user_dao, fake_message, session, fake_state
):
    """Тест: пользователь уже зарегистрирован."""
    mock_user_dao.find_one_or_none = AsyncMock(return_value={"telegram_id": 12345})

    from bot.config import settings_bot

    settings_bot.MESSAGES = {
        "modes": {
            "start": {
                "welcome": {
                    "first": ["Привет, {username}!", "Добро пожаловать!"],
                    "again": ["Снова привет, {username}!", "Рады видеть!"],
                }
            },
            "admin": {},
        },
        "errors": {},
    }

    await cmd_start(message=fake_message, command=None, state=fake_state)

    mock_user_dao.find_one_or_none.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(StartCommand.press_start)
    assert fake_message.answer.await_count == 2


@pytest.mark.asyncio
@patch("bot.users.router.bot")
async def test_admin_start_not_admin(mock_bot, fake_state):
    """Юнит-тест: пользователь не админ — доступ запрещён."""

    mock_bot.send_message = AsyncMock()

    fake_user = User(id=1111, is_bot=False, first_name="Test")
    fake_chat = Chat(id=1111, type="private")
    fake_message = MagicMock(spec=Message)
    fake_message.from_user = fake_user
    fake_message.chat = fake_chat
    fake_message.answer = AsyncMock()

    # Подменяем m_error
    m_error.clear()
    m_error.update({"admin_only": "Ошибка доступа"})

    await admin_start(message=fake_message, state=fake_state)

    fake_message.answer.assert_awaited_once()
    mock_bot.send_message.assert_awaited_once_with(
        text="Ошибка доступа",
        reply_markup=ReplyKeyboardRemove(),
        chat_id=1111,
    )

    fake_state.clear.assert_awaited_once()
    fake_state.set_state.assert_not_awaited()


@pytest.mark.asyncio
@patch("bot.users.router.bot")
async def test_admin_start_is_admin(mock_bot, fake_state):
    """Юнит-тест: пользователь является админом — получает сообщение и переходит в состояние."""

    # Замокаем асинхронный метод бота
    mock_bot.send_message = AsyncMock()

    # Создаём from_user и chat
    fake_user = User(id=9999, is_bot=False, first_name="Admin")
    fake_chat = Chat(id=9999, type="private")
    fake_message = MagicMock(spec=Message)
    fake_message.from_user = fake_user
    fake_message.chat = fake_chat
    fake_message.answer = AsyncMock()  # не будет вызвано, но на всякий случай

    # Настройка конфигурации
    from bot.config import settings_bot

    settings_bot.ADMIN_IDS = [9999]
    settings_bot.MESSAGES = {
        "modes": {"admin": {"on": "Привет, админ!", "off": "Нет доступа"}},
        "errors": {"admin_only": "Ошибка доступа"},
    }

    # Запуск обработчика
    await admin_start(message=fake_message, state=fake_state)

    # Проверки
    mock_bot.send_message.assert_awaited_once_with(
        chat_id=9999,
        text="Режим АДМИНА включён. Ты можешь использовать дополнительные функции.",
        reply_markup=ReplyKeyboardRemove(),
    )

    fake_state.clear.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(StartCommand.press_admin)
