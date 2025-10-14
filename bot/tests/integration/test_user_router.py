from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from bot.users.dao import RoleDAO, UserDAO
from bot.users.models import Role
from bot.users.models import User as DBUser
from bot.users.router import StartCommand, admin_start
from bot.users.router import cmd_start as user_router
from bot.users.schemas import SUserTelegramID


@pytest.mark.asyncio
async def test_cmd_start_new_user_real_db(fake_message, session, fake_state):
    """Интеграционный тест: новый пользователь сохраняется в реальную тестовую БД."""
    users_before = await UserDAO.find_all(session=session)
    assert len(users_before) == 0
    role_user = Role(name="user")
    session.add(role_user)
    await session.commit()

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
    settings_bot.ADMIN_IDS = [9999]

    raw_start = user_router.__wrapped__
    await raw_start(
        message=fake_message, command=None, session=session, state=fake_state
    )

    schema = SUserTelegramID(telegram_id=12345)
    user = await UserDAO.find_one_or_none(session=session, filters=schema)
    assert user is not None
    assert user.telegram_id == 12345

    roles = await RoleDAO.find_all(session=session)
    assert any(r.name == "user" for r in roles)

    fake_state.set_state.assert_awaited_once_with(StartCommand.press_start)
    assert fake_message.answer.await_count == 2


@pytest.mark.asyncio
async def test_cmd_start_existing_user_real_db(fake_message, session, fake_state):
    """Интеграционный тест: уже зарегистрированный пользователь вызывает /start."""
    exists_role = await session.scalar(select(Role).where(Role.name == "user"))
    if exists_role is None:
        role_user = Role(name="user")
        session.add(role_user)
        await session.commit()

    exists_user = await session.scalar(
        select(DBUser).where(DBUser.telegram_id == 12345)
    )
    if exists_user is None:
        user = DBUser(telegram_id=12345, username="test_user", first_name="Test User")
        session.add(user)
        await session.commit()

    users = await UserDAO.find_all(session=session)
    assert len(users) == 1
    assert users[0].telegram_id == 12345

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
    settings_bot.ADMIN_IDS = [9999]

    row_cmd = user_router.__wrapped__
    await row_cmd(message=fake_message, command=None, session=session, state=fake_state)

    users_after = await UserDAO.find_all(session=session)
    assert len(users_after) == 1  # запись та же, новых нет

    fake_state.set_state.assert_awaited_once_with(StartCommand.press_start)
    assert fake_message.answer.await_count == 2


@pytest.mark.asyncio
async def test_admin_start_not_admin_real_db(session, fake_state, monkeypatch):
    """Интеграционный тест: пользователь не админ — доступ запрещён."""

    test_user = DBUser(telegram_id=1111, username="testuser", first_name="Test")
    session.add(test_user)
    await session.commit()

    fake_message = MagicMock()
    fake_message.from_user = MagicMock(id=1111)
    fake_message.chat = MagicMock(id=1111)
    fake_message.answer = AsyncMock()

    from bot.config import settings_bot

    settings_bot.ADMIN_IDS = [9999]
    settings_bot.MESSAGES = {
        "modes": {"admin": {"off": "Нет доступа"}},
        "errors": {"admin_only": "Ошибка доступа"},
    }

    fake_send_message = AsyncMock()
    monkeypatch.setattr("bot.users.router.bot.send_message", fake_send_message)

    row_admin_start = admin_start.__wrapped__
    await row_admin_start(message=fake_message, session=session, state=fake_state)

    fake_message.answer.assert_awaited_once()
    fake_state.clear.assert_awaited_once()
    fake_state.set_state.assert_not_awaited()
    fake_send_message.assert_awaited_once()

    schema = SUserTelegramID(telegram_id=1111)
    db_user = await UserDAO.find_one_or_none(session=session, filters=schema)
    assert db_user is not None


@pytest.mark.asyncio
async def test_admin_start_is_admin_real_db(session, fake_state, monkeypatch):
    """Интеграционный тест: админ успешно проходит и получает сообщение."""

    test_user = DBUser(telegram_id=9999, username="adminuser", first_name="Admin")
    session.add(test_user)
    await session.commit()

    fake_message = MagicMock()
    fake_message.from_user = MagicMock(id=9999)
    fake_message.chat = MagicMock(id=9999)
    fake_message.answer = AsyncMock()

    from bot.config import settings_bot

    settings_bot.ADMIN_IDS = [9999]
    settings_bot.MESSAGES = {
        "modes": {"admin": {"on": "Добро пожаловать, админ!"}},
        "errors": {},
    }

    fake_send_message = AsyncMock()
    monkeypatch.setattr("bot.users.router.bot.send_message", fake_send_message)

    row_admin_start = admin_start.__wrapped__
    await row_admin_start(message=fake_message, session=session, state=fake_state)

    fake_state.clear.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(StartCommand.press_admin)

    fake_send_message.assert_awaited_once()

    schema = SUserTelegramID(telegram_id=9999)
    db_user = await UserDAO.find_one_or_none(session=session, filters=schema)
    assert db_user is not None
