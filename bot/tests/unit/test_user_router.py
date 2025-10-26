from unittest.mock import AsyncMock

import pytest

from bot.config import settings_bot
from bot.users.router import (
    UserRouter,
    UserStates,
)


@pytest.mark.asyncio
@pytest.mark.users
async def test_cmd_start_new_user_monkeypatch(
    fake_bot,
    fake_logger,
    fake_redis,
    make_fake_message,
    fake_state,
    session,
    monkeypatch,
):
    """Тест обработчика /start для нового пользователя через monkeypatch."""

    router = UserRouter(bot=fake_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=123)
    # Мокаем UserDAO.find_one_or_none чтобы вернуть None (новый пользователь)
    async_mock_find = AsyncMock(return_value=None)
    monkeypatch.setattr("bot.users.router.UserDAO.find_one_or_none", async_mock_find)

    # Мокаем UserDAO.add_role_subscription, чтобы вернуть мок-экземпляр нового пользователя
    async_mock_add = AsyncMock()
    monkeypatch.setattr(
        "bot.users.router.UserDAO.add_role_subscription", async_mock_add
    )

    # Вызываем метод
    await router.cmd_start(message=fake_message, session=session, state=fake_state)

    # Проверяем, что метод answer был вызван хотя бы один раз
    assert fake_message.answer.await_count >= 1

    # Проверяем, что состояние установлено в press_start
    fake_state.set_state.assert_awaited_with(UserStates.press_start)

    # Проверяем, что UserDAO.find_one_or_none вызван с session
    async_mock_find.assert_awaited()
    # Проверяем, что UserDAO.add_role_subscription вызван
    async_mock_add.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_with_admin_monkeypatch(
    fake_bot, fake_logger, fake_redis, make_fake_message, fake_state, monkeypatch
):
    """Тест обработчика /admin для админа через monkeypatch."""

    router = UserRouter(bot=fake_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=123)
    # Настраиваем пользователя как админа
    from bot.config import settings_bot

    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123])

    # Вызываем метод
    await router.admin_start(message=fake_message, state=fake_state)

    # Проверяем, что состояние установлено в press_admin
    fake_state.set_state.assert_awaited_with(UserStates.press_admin)

    # Проверяем, что бот отправил сообщения (send_message)
    assert fake_bot.send_message.await_count >= 1


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_non_admin_monkeypatch(
    fake_bot, fake_logger, fake_redis, make_fake_message, fake_state, monkeypatch
):
    """Тест обработчика /admin для обычного пользователя через monkeypatch."""

    router = UserRouter(bot=fake_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=999)
    # Настраиваем пользователя не админом
    from bot.config import settings_bot

    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123])

    # Вызываем метод
    await router.admin_start(message=fake_message, state=fake_state)

    # Проверяем, что состояние НЕ установлено
    fake_state.set_state.assert_not_awaited()

    # Проверяем, что сообщение об ошибке отправлено
    fake_message.answer.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_start(
    make_fake_message, fake_bot, fake_logger, fake_redis, fake_state
):
    router = UserRouter(bot=fake_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message()

    fake_state.get_state.return_value = "UserStates:press_start"

    await router.mistake_handler_user(fake_message, fake_state)

    fake_message.delete.assert_awaited()
    # Проверяем, что отправлено правильное уведомление
    expected_text = settings_bot.MESSAGES["errors"]["unknown_command"]
    fake_message.answer.assert_awaited_with(text=expected_text)


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_admin(
    make_fake_message, fake_bot, fake_logger, fake_redis, fake_state
):
    router = UserRouter(bot=fake_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message()

    fake_state.get_state.return_value = "UserStates:press_admin"

    await router.mistake_handler_user(fake_message, fake_state)

    fake_message.delete.assert_awaited()
    # Проверяем отправку правильного текста для админа
    expected_text = settings_bot.MESSAGES["errors"]["unknown_command_admin"]
    fake_message.answer.assert_awaited_with(text=expected_text)
