from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message

from bot.config import settings_bot
from bot.users.dao import UserDAO
from bot.users.models import User
from bot.users.router import (
    UserStates,
    admin_start,
    cmd_start,
    mistake_handler_user,
    user_router,
)
from bot.users.schemas import SRole, SUser, SUserTelegramID


@pytest.mark.asyncio
@pytest.mark.users
async def test_cmd_start_new_user(session, monkeypatch):
    """Тест для /start с новым пользователем"""

    # Мок чата
    mock_chat = AsyncMock()
    mock_chat.id = 123

    # Мок пользователя Telegram
    mock_from_user = SimpleNamespace(
        id=999,
        username="testuser",
        first_name="Test",
        last_name="User",
        full_name="Test User",
    )

    # Мок сообщения
    mock_message = AsyncMock()
    mock_message.chat = mock_chat
    mock_message.from_user = mock_from_user
    mock_message.answer = AsyncMock()
    mock_message.delete = AsyncMock()

    # Мок FSMContext
    mock_state = AsyncMock(spec=FSMContext)

    # Мокаем UserDAO
    monkeypatch.setattr(UserDAO, "find_one_or_none", AsyncMock(return_value=None))
    mock_role = SimpleNamespace(name="user")
    mock_add_user = AsyncMock(
        return_value=SimpleNamespace(
            subscription=SimpleNamespace(is_active=True),
            first_name="Test",
            last_name="User",
            username="testuser",
            telegram_id=999,
            roles=[mock_role],
        )
    )
    monkeypatch.setattr(UserDAO, "add_role_subscription", mock_add_user)

    # **Мокаем send_to_admins**, чтобы не обращаться к Redis и не сериализовать AsyncMock
    monkeypatch.setattr("bot.users.router.send_to_admins", AsyncMock())

    # Вызываем хендлер
    await cmd_start(message=mock_message, command=Mock(), state=mock_state)

    # Проверяем, что отправлены сообщения
    assert mock_message.answer.call_count >= 2

    # Проверяем, что пользователь добавлен через DAO
    mock_add_user.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_non_admin(monkeypatch):
    """Тест /admin для неадмина"""

    # Мок пользователя Telegram
    mock_from_user = SimpleNamespace(
        id=123, username="testuser"  # id не в settings_bot.ADMIN_IDS
    )
    # Мок чата
    mock_chat = SimpleNamespace(id=123)
    # Мок сообщения
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = mock_from_user
    mock_message.chat = mock_chat
    mock_message.answer = AsyncMock()

    # Мок FSMContext
    mock_state = AsyncMock(spec=FSMContext)
    monkeypatch.setattr("bot.users.router.bot.send_message", AsyncMock())
    # Вызываем обработчик
    await admin_start(mock_message, state=mock_state)

    # Проверяем, что пользователь получил сообщение об ошибке
    mock_message.answer.assert_awaited()
    mock_state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_admin(monkeypatch):
    """Тест /admin для админа"""

    # Добавляем id пользователя в список админов
    admin_id = 999
    settings_bot.ADMIN_IDS.append(admin_id)

    # Мок пользователя Telegram
    mock_from_user = SimpleNamespace(id=admin_id, username="adminuser")
    # Мок чата
    mock_chat = SimpleNamespace(id=123)

    # Мок сообщения
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = mock_from_user
    mock_message.chat = mock_chat
    mock_message.answer = AsyncMock()

    # Мок FSMContext
    mock_state = AsyncMock(spec=FSMContext)
    # Мокаем bot.send_message, чтобы не уходил реальный запрос
    monkeypatch.setattr("bot.users.router.bot.send_message", AsyncMock())

    # Вызываем обработчик
    await admin_start(mock_message, state=mock_state)

    # Проверяем, что сообщения отправлены и FSM состояние установлено
    # mock_message.answer.assert_awaited()
    mock_state.set_state.assert_awaited_with(UserStates.press_admin)

    # Чистим изменения в ADMIN_IDS
    settings_bot.ADMIN_IDS.remove(admin_id)


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_start(monkeypatch):
    """Тест для mistake_handler_user в состоянии press_start"""
    monkeypatch.setattr(
        "bot.users.router.m_error",
        {
            "unknown_command": "⚠️ Произошла ошибка. Попробуйте позже.",
            "unknown_command_admin": "⚠️ Неверная команда для режима админа.",
        },
    )
    # Мок пользователя Telegram
    mock_from_user = SimpleNamespace(id=999, username="testuser")

    # Мок чата
    mock_chat = SimpleNamespace(id=123)

    # Мок сообщения
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = mock_from_user
    mock_message.chat = mock_chat
    mock_message.answer = AsyncMock()
    mock_message.delete = AsyncMock()

    # Мок FSMContext, возвращаем состояние press_start
    mock_state = AsyncMock(spec=FSMContext)
    mock_state.get_state.return_value = "UserStates:press_start"

    # Вызываем обработчик
    await mistake_handler_user(mock_message, state=mock_state)

    # Проверяем, что сообщение удалилось
    mock_message.delete.assert_awaited_once()

    # Проверяем удаление и отправку сообщения
    mock_message.delete.assert_awaited_once()
    mock_message.answer.assert_awaited_once_with(
        text="⚠️ Произошла ошибка. Попробуйте позже."
    )


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_admin(monkeypatch):
    """Тест для mistake_handler_user в состоянии press_admin"""
    # Мокируем словарь ошибок
    monkeypatch.setattr(
        "bot.users.router.m_error",
        {
            "unknown_command": "⚠️ Произошла ошибка. Попробуйте позже.",
            "unknown_command_admin": "⚠️ Неверная команда для режима админа.",
        },
    )

    # Мок пользователя Telegram
    mock_from_user = SimpleNamespace(id=999, username="testuser")

    # Мок чата
    mock_chat = SimpleNamespace(id=123)

    # Мок сообщения
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = mock_from_user
    mock_message.chat = mock_chat
    mock_message.answer = AsyncMock()
    mock_message.delete = AsyncMock()
    # Мок FSMContext, возвращаем состояние press_admin
    mock_state = AsyncMock(spec=FSMContext)
    mock_state.get_state.return_value = "UserStates:press_admin"

    # Вызываем обработчик
    await mistake_handler_user(mock_message, state=mock_state)

    # Проверяем удаление и отправку сообщения
    mock_message.delete.assert_awaited_once()
    mock_message.answer.assert_awaited_once_with(
        text="⚠️ Неверная команда для режима админа."
    )
