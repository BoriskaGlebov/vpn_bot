from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.types import User as TGUser

from bot.referrals.router import ReferralRouter
from bot.utils.base_router import BaseRouter


@pytest.mark.asyncio
async def test_invite_handler_calls_answer_and_clear(
    fake_bot, fake_logger, make_fake_message, fake_state, tg_user
):
    # Мок для bot.get_me()
    fake_bot.get_me.return_value.username = "test_bot"

    # Создаем router
    router = ReferralRouter(bot=fake_bot, logger=fake_logger)

    # Мок message и state
    mock_message = make_fake_message()
    mock_state = fake_state

    # Вызов метода
    await router.invite_handler(message=mock_message, state=mock_state)

    # Проверяем, что state.clear() вызван
    mock_state.clear.assert_awaited_once()

    # Проверяем, что bot.get_me() вызван
    fake_bot.get_me.assert_awaited_once()

    # Проверяем, что message.answer вызван с текстом и клавиатурой
    mock_message.answer.assert_awaited_once()
    args, kwargs = mock_message.answer.call_args
    assert "text" in kwargs
    assert (
        kwargs["text"] is not None
    )  # текст берется из settings_bot.messages.modes.referrals.invite
    assert "reply_markup" in kwargs
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_invite_handler_reply_markup_contains_username_and_userid(
    fake_bot, fake_logger, make_fake_message, fake_state, tg_user
):
    mock_bot = fake_bot
    mock_bot.get_me.return_value.username = "test_bot"
    mock_logger = fake_logger
    router = ReferralRouter(bot=mock_bot, logger=mock_logger)

    mock_message = make_fake_message()
    mock_state = fake_state
    mock_user = tg_user

    # Патчим функцию referral_kb через MagicMock
    from bot.referrals.keyboards.inline_kb import referral_kb

    router.referral_kb = AsyncMock(return_value="keyboard")  # если бы был метод
    # Но у нас referral_kb импортируется напрямую, можно замокать через patch
    import bot.referrals.router as routers_module

    routers_module.referral_kb = MagicMock(return_value="keyboard")

    await router.invite_handler(message=mock_message, state=mock_state)

    args, kwargs = mock_message.answer.call_args
    assert kwargs["reply_markup"] == "keyboard"
    # Проверяем, что referral_kb вызвана с правильными аргументами
    routers_module.referral_kb.assert_called_once_with("test_bot", 123)
