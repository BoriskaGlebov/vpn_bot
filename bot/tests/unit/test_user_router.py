from unittest.mock import AsyncMock

import pytest
from aiogram.types import ReplyKeyboardRemove

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
):
    """Тест обработчика /start для нового пользователя через мок UserService."""

    fake_message = make_fake_message(user_id=123)

    # Создаём мок user_service
    class FakeSubscription:
        is_active = True

    class FakeUserOut:
        id = 123
        telegram_id = 123
        username = "test_user"
        first_name = "Test"
        last_name = "User"
        subscription = FakeSubscription()
        role = type("FakeRole", (), {"name": "user"})()

    fake_user_service = AsyncMock()
    fake_user_service.register_or_get_user.return_value = (
        FakeUserOut(),
        True,
    )  # новый пользователь

    # Создаём роутер
    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=fake_user_service,
    )

    # Запуск хендлера
    await router.cmd_start(message=fake_message, session=session, state=fake_state)

    # Проверки
    fake_user_service.register_or_get_user.assert_awaited_once_with(
        session=session, telegram_user=fake_message.from_user
    )
    fake_message.answer.assert_awaited()  # хотя бы одно сообщение отправлено
    fake_state.set_state.assert_awaited_once_with(UserStates.press_start)


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_with_admin_monkeypatch(
    fake_bot, fake_logger, fake_redis, make_fake_message, fake_state, monkeypatch
):
    """Тест обработчика /admin для админа через мок."""

    fake_message = make_fake_message(user_id=123)

    # Настраиваем пользователя как админа
    from bot.config import settings_bot

    monkeypatch.setattr(settings_bot, "admin_ids", {123})

    # Создаём роутер с моками
    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),  # для unit-теста можно просто мок
    )

    # Вызов хендлера
    await router.admin_start(message=fake_message, state=fake_state)

    # Проверки
    fake_state.set_state.assert_awaited_once_with(UserStates.press_admin)
    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_non_admin_monkeypatch(
    fake_bot, fake_logger, fake_redis, make_fake_message, fake_state, monkeypatch
):
    """Тест обработчика /admin для обычного пользователя (не админ)."""

    fake_message = make_fake_message(user_id=999)

    # Настраиваем ADMIN_IDS так, чтобы пользователь не был админом
    from bot.config import settings_bot

    monkeypatch.setattr(settings_bot, "admin_ids", {123})

    # Создаём роутер с моками
    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),
    )

    # Вызов хендлера
    await router.admin_start(message=fake_message, state=fake_state)

    # Проверки
    # Состояние не должно устанавливаться
    fake_state.set_state.assert_not_awaited()
    # Сообщение пользователю об ошибке отправлено
    fake_message.answer.assert_awaited()
    # Бот отправил предупреждение пользователю
    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_start(
    make_fake_message, fake_bot, fake_logger, fake_redis, fake_state
):
    # Подготовка
    fake_message = make_fake_message()

    fake_state.get_state = AsyncMock(return_value="UserStates:press_start")

    # Создаём роутер с моком user_service
    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),  # просто мок
    )

    # Вызов метода
    await router.mistake_handler_user(fake_message, fake_state)

    # Проверки
    fake_message.delete.assert_awaited()
    expected_text = settings_bot.messages["errors"]["unknown_command"]
    fake_message.answer.assert_awaited_with(text=expected_text)


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_admin(
    make_fake_message, fake_bot, fake_logger, fake_redis, fake_state
):
    # Подготовка
    fake_message = make_fake_message()

    fake_state.get_state = AsyncMock(return_value="UserStates:press_admin")
    fake_state.get_data = AsyncMock(
        side_effect=[
            {"press_admin": 0},  # первый вызов
            {"press_admin": 1},  # второй вызов
        ]
    )

    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),  # мок
    )

    # Первый вызов — обычная неизвестная команда
    await router.mistake_handler_user(fake_message, fake_state)
    fake_message.delete.assert_awaited()
    expected_text = settings_bot.messages["errors"]["unknown_command"]
    fake_message.answer.assert_awaited_with(text=expected_text)

    # Сброс моков перед вторым вызовом
    fake_message.answer.reset_mock()
    fake_message.delete.reset_mock()

    # Второй вызов — превышение лимита
    await router.mistake_handler_user(fake_message, fake_state)
    expected_text = settings_bot.messages["errors"]["help_limit_reached"].format(
        username=f"@{fake_message.from_user.username}"
    )
    fake_message.answer.assert_awaited_with(
        text=expected_text, reply_markup=ReplyKeyboardRemove()
    )
    fake_message.delete.assert_awaited()
