from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from loguru import logger as real_logger

from bot.config import settings_bot
from bot.utils import commands


@pytest.fixture
def fake_bot():
    bot = AsyncMock(spec=Bot)
    bot.get_me.return_value.first_name = "TestBot"
    bot.set_my_description.return_value = None
    return bot


@pytest.fixture
def fake_logger(monkeypatch):
    logger = MagicMock(spec=real_logger)
    logger.bind.return_value = logger
    monkeypatch.setattr("bot.config.logger", logger)
    return logger


@pytest.fixture
def patch_deps(fake_bot, fake_logger, monkeypatch):
    monkeypatch.setattr(commands, "bot", fake_bot)
    monkeypatch.setattr(commands, "logger", fake_logger)
    monkeypatch.setattr(settings_bot, "MESSAGES", {"description": "описание"})
    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123, 456])
    return fake_bot, fake_logger
