# tests/conftest.py
from pathlib import Path

import pytest
from aiogram import Bot

from bot.config import SettingsBot
from bot.config import bot as real_bot

# Загружаем тестовый .env
# load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / ".env.test")


@pytest.fixture
async def test_bot():
    """Фикстура для интеграционного теста с тестовым ботом."""

    # Подменяем настройки бота на тестовые
    test_settings = SettingsBot(
        _env_file=Path(__file__).resolve().parent.parent.parent.parent / ".env.test"
    )
    test_admin_id = test_settings.ADMIN_IDS[0]  # Берем первый админ ID из .env.test

    # Создаем тестового бота
    bot_instance = Bot(token=test_settings.BOT_TOKEN.get_secret_value())

    # Патчим глобальный бот в коде на тестовый
    real_bot.__class__ = bot_instance.__class__
    real_bot.__dict__ = bot_instance.__dict__

    yield real_bot, test_admin_id, test_settings

    # Закрываем сессию после теста
    await bot_instance.session.close()
