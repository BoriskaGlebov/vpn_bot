from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardRemove

from bot.core.config import settings_bot
from bot.referrals.services import ReferralService
from bot.users.router import UserRouter, UserStates


@pytest.mark.asyncio
@pytest.mark.users
async def test_cmd_start_new_user_monkeypatch(
    fake_bot: Any,
    fake_logger: Any,
    fake_redis: Any,
    make_fake_message: Any,
    fake_state: Any,
) -> None:
    """Проверяет обработчик /start для нового пользователя.

    Сценарий:
        - пользователь вызывает /start;
        - сервис возвращает нового пользователя;
        - бот отправляет ответ;
        - устанавливается состояние press_start.

    Проверяется:
        - вызов user_service;
        - отправка сообщения;
        - установка состояния.
    """

    fake_message = make_fake_message(user_id=123)
    command_obj = CommandStart()

    class FakeSubscription:
        is_active: bool = True

    class FakeUserOut:
        id: int = 123
        telegram_id: int = 123
        username: str = "test_user"
        first_name: str = "Test"
        last_name: str = "User"
        subscriptions: list[Any] = [FakeSubscription()]
        current_subscription: Any = FakeSubscription()
        role: Any = type("FakeRole", (), {"name": "user"})()

    fake_user_service = AsyncMock()
    fake_user_service.register_or_get_user.return_value = (FakeUserOut(), True)

    referral_service = AsyncMock(spec=ReferralService)

    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=fake_user_service,
        referral_service=referral_service,
    )

    await router.cmd_start(
        message=fake_message,
        state=fake_state,
        command=command_obj,
    )

    fake_user_service.register_or_get_user.assert_awaited_once_with(
        telegram_user=fake_message.from_user
    )

    fake_message.answer.assert_awaited()
    fake_state.set_state.assert_awaited_once_with(UserStates.press_start)


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_with_admin_monkeypatch(
    fake_bot: Any,
    fake_logger: Any,
    fake_redis: Any,
    make_fake_message: Any,
    fake_state: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет доступ к /admin для администратора.

    Сценарий:
        - пользователь находится в списке admin_ids;
        - вызывается admin handler.

    Проверяется:
        - установка состояния press_admin;
        - отправка сообщения через bot.
    """

    fake_message = make_fake_message(user_id=123)

    monkeypatch.setattr(settings_bot, "admin_ids", {123})

    referral_service = AsyncMock(spec=ReferralService)

    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),
        referral_service=referral_service,
    )

    await router.admin_start(message=fake_message, state=fake_state)

    fake_state.set_state.assert_awaited_once_with(UserStates.press_admin)
    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_non_admin_monkeypatch(
    fake_bot: Any,
    fake_logger: Any,
    fake_redis: Any,
    make_fake_message: Any,
    fake_state: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет отказ в доступе к /admin для обычного пользователя.

    Сценарий:
        - пользователь отсутствует в admin_ids.

    Проверяется:
        - состояние не устанавливается;
        - пользователю отправляется сообщение об ошибке;
        - бот уведомляет пользователя.
    """

    fake_message = make_fake_message(user_id=999)

    monkeypatch.setattr(settings_bot, "admin_ids", {123})

    referral_service = AsyncMock(spec=ReferralService)

    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),
        referral_service=referral_service,
    )

    await router.admin_start(message=fake_message, state=fake_state)

    fake_state.set_state.assert_not_awaited()
    fake_message.answer.assert_awaited()
    fake_bot.send_message.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_start(
    make_fake_message: Any,
    fake_bot: Any,
    fake_logger: Any,
    fake_redis: Any,
    fake_state: Any,
) -> None:
    """Проверяет обработку неизвестной команды в состоянии press_start.

    Сценарий:
        - пользователь в состоянии press_start;
        - отправляет неизвестную команду.

    Проверяется:
        - сообщение удаляется;
        - отправляется стандартное сообщение об ошибке.
    """

    fake_message = make_fake_message()

    fake_state.get_state = AsyncMock(return_value="UserStates:press_start")

    referral_service = AsyncMock(spec=ReferralService)

    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),
        referral_service=referral_service,
    )

    await router.mistake_handler_user(fake_message, fake_state)

    fake_message.delete.assert_awaited()

    expected_text: str = settings_bot.messages["errors"]["unknown_command"]

    fake_message.answer.assert_awaited_with(text=expected_text)


@pytest.mark.asyncio
@pytest.mark.users
async def test_mistake_handler_user_press_admin(
    make_fake_message: Any,
    fake_bot: Any,
    fake_logger: Any,
    fake_redis: Any,
    fake_state: Any,
) -> None:
    """Проверяет обработку ошибок в состоянии press_admin с лимитом.

    Сценарий:
        1. Первая ошибка:
            - стандартный ответ "unknown_command".
        2. Повторная ошибка:
            - превышен лимит;
            - отправляется сообщение с ограничением и удаляется клавиатура.

    Проверяется:
        - корректное переключение поведения;
        - удаление сообщения;
        - форматирование текста с username.
    """

    fake_message = make_fake_message()

    fake_state.get_state = AsyncMock(return_value="UserStates:press_admin")

    fake_state.get_data = AsyncMock(
        side_effect=[
            {"press_admin": 0},
            {"press_admin": 1},
        ]
    )

    referral_service = AsyncMock(spec=ReferralService)

    router = UserRouter(
        bot=fake_bot,
        logger=fake_logger,
        redis_manager=fake_redis,
        user_service=AsyncMock(),
        referral_service=referral_service,
    )

    # Первый вызов
    await router.mistake_handler_user(fake_message, fake_state)

    fake_message.delete.assert_awaited()

    expected_text_1: str = settings_bot.messages["errors"]["unknown_command"]

    fake_message.answer.assert_awaited_with(text=expected_text_1)

    # Сброс моков
    fake_message.answer.reset_mock()
    fake_message.delete.reset_mock()

    # Второй вызов (лимит)
    await router.mistake_handler_user(fake_message, fake_state)

    expected_text_2: str = settings_bot.messages["errors"]["help_limit_reached"].format(
        username=f"@{fake_message.from_user.username}"
    )

    fake_message.answer.assert_awaited_with(
        text=expected_text_2,
        reply_markup=ReplyKeyboardRemove(),
    )

    fake_message.delete.assert_awaited()
