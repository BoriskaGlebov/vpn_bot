from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message

from bot.config import settings_bot
from bot.middleware.exception_middleware import ErrorHandlerMiddleware


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_middleware_handles_message_exception(monkeypatch):
    mw = ErrorHandlerMiddleware()

    async def fake_handler(event, data):
        raise TelegramBadRequest("invalid request")

    # Мокаем Message и from_user
    fake_from_user = MagicMock()
    fake_from_user.id = 123

    fake_message = MagicMock(spec=Message)
    fake_message.from_user = fake_from_user
    fake_message.reply = AsyncMock()
    monkeypatch.setattr(
        settings_bot, "MESSAGES", {"general": {"common_error": "Тестовая ошибка"}}
    )
    await mw(fake_handler, fake_message, {})

    fake_message.reply.assert_awaited_once()
    sent_text = fake_message.reply.call_args[0][0]
    assert "Тестовая ошибка" in sent_text


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_middleware_handles_callback_query_exception(monkeypatch):
    mw = ErrorHandlerMiddleware()

    async def fake_handler(event, data):
        raise TelegramRetryAfter(retry_after=10)

    fake_from_user = MagicMock()
    fake_from_user.id = 456

    fake_message = MagicMock()
    fake_message.answer = AsyncMock()

    fake_query = MagicMock(spec=CallbackQuery)
    fake_query.from_user = fake_from_user
    fake_query.message = fake_message
    monkeypatch.setattr(
        settings_bot, "MESSAGES", {"general": {"common_error": "Тестовая ошибка"}}
    )
    await mw(fake_handler, fake_query, {})

    fake_message.answer.assert_awaited_once()
    sent_text = fake_message.answer.call_args[0][0]
    assert "Тестовая ошибка" in sent_text


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_middleware_logs_exception(monkeypatch):
    mw = ErrorHandlerMiddleware()

    async def fake_handler(event, data):
        raise Exception("generic error")

    # Создаём from_user отдельно
    fake_from_user = MagicMock()
    fake_from_user.id = 789

    fake_message = MagicMock(spec=Message)
    fake_message.from_user = fake_from_user
    fake_message.reply = AsyncMock()

    # Мокаем logger
    mock_logger = MagicMock()
    monkeypatch.setattr("bot.middleware.exception_middleware.logger", mock_logger)

    await mw(fake_handler, fake_message, {})

    fake_message.reply.assert_awaited_once()
    mock_logger.bind.assert_called_with(user=789)
    mock_logger.bind().exception.assert_called()
