from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import SettingsBot
from bot.config import bot as real_bot


@pytest.fixture(scope="session")
def test_settings_bot() -> SettingsBot:
    """Фикстура для загрузки тестовых настроек из .env.test."""
    return SettingsBot(
        _env_file=Path(__file__).resolve().parent.parent.parent.parent / ".env.test"
    )


@pytest.fixture(scope="session")
def test_admin_id(test_settings_bot: SettingsBot) -> int:
    """Фикстура для получения ID администратора из настроек."""
    return test_settings_bot.ADMIN_IDS[0]


@pytest.fixture(scope="session")
async def test_bot(test_settings_bot: SettingsBot) -> AsyncGenerator[Bot, Any]:
    """Фикстура для интеграционных тестов с тестовым ботом."""
    bot_instance = Bot(
        token=test_settings_bot.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Патчим глобальный бот, чтобы код использовал именно тестовый экземпляр
    real_bot.__class__ = bot_instance.__class__
    real_bot.__dict__ = bot_instance.__dict__

    yield bot_instance

    await bot_instance.session.close()
