from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.utils import (
    start_stop_bot as start_module,  # <-- или правильный модуль, где start_bot
)


@pytest.mark.asyncio
@pytest.mark.utils
async def test_start_bot_sends_messages_and_logs(monkeypatch, fake_bot, fake_logger):
    # --- Arrange ---
    # Мокаем set_bot_commands и set_description
    monkeypatch.setattr(start_module, "set_bot_commands", AsyncMock())
    monkeypatch.setattr(start_module, "set_description", AsyncMock())

    # Делаем так, чтобы один из админов "падал" при отправке
    fake_bot.send_message = AsyncMock(
        side_effect=[
            None,  # для первого админа успешно
            TelegramBadRequest(method="send_message", message="ошибка"),  # для второго
        ]
    )

    # Подменяем список админов
    monkeypatch.setattr(start_module.settings_bot, "ADMIN_IDS", [111, 222])

    # # Подменяем бот внутри модуля старта
    monkeypatch.setattr(start_module, "bot", fake_bot)
    monkeypatch.setattr(start_module, "logger", fake_logger)

    # --- Act ---
    await start_module.start_bot()

    # --- Assert ---
    start_module.set_bot_commands.assert_awaited_once()
    start_module.set_description.assert_awaited_once_with(bot=fake_bot)

    # Проверяем, что бот пытался отправить два сообщения
    assert fake_bot.send_message.await_count == 2
    fake_bot.send_message.assert_any_await(111, "Я запущен🥳.")
    fake_bot.send_message.assert_any_await(222, "Я запущен🥳.")

    # Проверяем, что ошибка залогировалась
    fake_logger.bind.assert_called_with(user=222)
    fake_logger.bind.return_value.error.assert_called_once()

    # Проверяем, что финальный лог об успешном запуске есть
    fake_logger.info.assert_called_with("Бот успешно запущен.")


@pytest.mark.asyncio
@pytest.mark.utils
async def test_stop_bot_sends_messages_and_logs(monkeypatch, fake_bot, fake_logger):
    """
    Проверяет, что stop_bot отправляет сообщения всем админам
    и логирует факт остановки.
    """

    # Подготовка — моки
    fake_bot.send_message = AsyncMock()
    fake_logger.bind.return_value = fake_logger

    # Настраиваем админов
    monkeypatch.setattr(start_module.settings_bot, "ADMIN_IDS", [1, 2, 3])

    # Подменяем зависимости в модуле старта
    monkeypatch.setattr(start_module, "bot", fake_bot)
    monkeypatch.setattr(start_module, "logger", fake_logger)

    # Запускаем тестируемую корутину
    await start_module.stop_bot()

    # Проверяем, что send_message вызвали для всех админов
    fake_bot.send_message.assert_any_await(1, "Бот остановлен. За что?😔")
    fake_bot.send_message.assert_any_await(2, "Бот остановлен. За что?😔")
    fake_bot.send_message.assert_any_await(3, "Бот остановлен. За что?😔")
    assert fake_bot.send_message.await_count == 3

    # Проверяем, что логгер зафиксировал остановку
    fake_logger.error.assert_any_call("Бот остановлен!")


@pytest.mark.asyncio
@pytest.mark.utils
async def test_stop_bot_handles_telegram_bad_request(
    monkeypatch, fake_bot, fake_logger
):
    """Проверяет, что stop_bot корректно логирует ошибки отправки сообщений."""

    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="send_message", message="bad request")

    fake_bot.send_message = AsyncMock(side_effect=raise_bad_request)
    fake_logger.bind.return_value = fake_logger

    monkeypatch.setattr(
        start_module.settings_bot,
        "ADMIN_IDS",
        [
            42,
        ],
    )
    monkeypatch.setattr(start_module, "bot", fake_bot)
    monkeypatch.setattr(start_module, "logger", fake_logger)

    await start_module.stop_bot()

    # Проверяем, что logger.bind().error был вызван
    fake_logger.bind.assert_called_with(user=42)
    # Проверяем, что error() вызывался с конкретным сообщением
    expected_msg = "Не удалось отправить сообщение админу 42 об остановке бота: Telegram server says - bad request"
    fake_logger.error.assert_any_call(expected_msg)
    fake_logger.error.assert_any_call("Бот остановлен!")
