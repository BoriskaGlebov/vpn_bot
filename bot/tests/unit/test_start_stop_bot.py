from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

import bot.config as config
from bot.utils import start_stop_bot as start_module


@pytest.mark.asyncio
@pytest.mark.utils
async def test_start_bot_sends_messages_and_logs(monkeypatch, fake_bot, fake_logger):
    monkeypatch.setattr(start_module, "set_bot_commands", AsyncMock())
    monkeypatch.setattr(start_module, "set_description", AsyncMock())
    monkeypatch.setattr(start_module, "send_to_admins", AsyncMock())

    fake_bot.send_message = AsyncMock(
        side_effect=[
            None,
            TelegramBadRequest(method="send_message", message="ошибка"),  # для второго
        ]
    )

    monkeypatch.setattr(start_module.settings_bot, "ADMIN_IDS", [111, 222])
    monkeypatch.setattr(start_module, "logger", fake_logger)

    # Act
    await start_module.start_bot(bot=fake_bot)

    # Assert
    start_module.set_bot_commands.assert_awaited_once()
    start_module.set_description.assert_awaited_once_with(bot=fake_bot)
    start_module.send_to_admins.assert_awaited_once_with(
        bot=fake_bot, message_text="Я запущен🥳."
    )
    fake_logger.info.assert_called_with("Бот успешно запущен.")


@pytest.mark.asyncio
@pytest.mark.utils
async def test_stop_bot_sends_messages_and_logs(monkeypatch, fake_bot, fake_logger):
    fake_bot.send_message = AsyncMock()
    fake_logger.bind.return_value = fake_logger

    monkeypatch.setattr(start_module.settings_bot, "ADMIN_IDS", [1, 2, 3])

    monkeypatch.setattr(start_module, "logger", fake_logger)
    monkeypatch.setattr(start_module, "send_to_admins", AsyncMock())

    # act
    await start_module.stop_bot(bot=fake_bot)

    # assert
    start_module.send_to_admins.assert_awaited_once_with(
        bot=fake_bot, message_text="Бот остановлен. За что?😔"
    )
    start_module.send_to_admins.assert_awaited_once
    fake_logger.error.assert_any_call("Бот остановлен!")


@pytest.mark.asyncio
@pytest.mark.utils
async def test_send_to_admins_logs_bad_request(monkeypatch, fake_bot, fake_logger):
    # Arrange
    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="send_message", message="bad request")

    fake_bot.send_message = AsyncMock(side_effect=raise_bad_request)
    fake_logger.bind.return_value = fake_logger

    monkeypatch.setattr(start_module.settings_bot, "ADMIN_IDS", [42])
    monkeypatch.setattr(start_module, "logger", fake_logger)

    # Act — здесь исключение ловится внутри send_to_admins()
    await start_module.send_to_admins(
        bot=fake_bot, message_text="Бот остановлен. За что?😔"
    )

    # Assert
    fake_logger.bind.assert_called_with(user=42)
    fake_logger.error.assert_called_once_with(
        "Не удалось отправить сообщение админу 42: Telegram server says - bad request"
    )


@pytest.mark.asyncio
@pytest.mark.utils
async def test_send_to_admins_success(monkeypatch, fake_bot):
    fake_bot.send_message = AsyncMock()

    monkeypatch.setattr(start_module.settings_bot, "ADMIN_IDS", [1, 2])

    await start_module.send_to_admins(bot=fake_bot, message_text="Привет админы!")

    assert fake_bot.send_message.await_count == 2
    fake_bot.send_message.assert_any_await(
        chat_id=1, text="Привет админы!", reply_markup=None
    )
    fake_bot.send_message.assert_any_await(
        chat_id=2, text="Привет админы!", reply_markup=None
    )


@pytest.mark.asyncio
@pytest.mark.utils
async def test_send_to_admins_handles_bad_request(monkeypatch, fake_logger, fake_bot):
    # Arrange
    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="send_message", message="bad request")

    fake_bot.send_message = AsyncMock(side_effect=raise_bad_request)

    # Подменяем ADMIN_IDS на нужные ID
    monkeypatch.setattr("bot.utils.start_stop_bot.logger", fake_logger)
    monkeypatch.setattr(config.settings_bot, "ADMIN_IDS", [42])
    await start_module.send_to_admins(bot=fake_bot, message_text="Тест")

    assert fake_bot.send_message.await_count == 1
    fake_logger.bind.assert_called_with(user=42)
    fake_logger.error.assert_called_once_with(
        "Не удалось отправить сообщение админу 42: Telegram server says - bad request"
    )


@pytest.mark.asyncio
@pytest.mark.utils
async def test_edit_admin_messages_success(monkeypatch, fake_bot, fake_redis):
    # fake_bot = AsyncMock()
    fake_redis.get_admin_messages = AsyncMock(
        return_value=[
            {"chat_id": 1, "message_id": 101},
            {"chat_id": 2, "message_id": 102},
        ]
    )
    fake_redis.clear_admin_messages = AsyncMock()

    await start_module.edit_admin_messages(
        bot=fake_bot, user_id=10, new_text="Новый текст", redis_manager=fake_redis
    )

    assert fake_bot.edit_message_text.await_count == 2
    fake_redis.clear_admin_messages.assert_awaited_once_with(10)


@pytest.mark.asyncio
@pytest.mark.utils
async def test_edit_admin_messages_handles_bad_request(
    monkeypatch, fake_logger, fake_bot, fake_redis
):
    fake_redis.get_admin_messages = AsyncMock(
        return_value=[
            {"chat_id": 1, "message_id": 101},
        ]
    )
    fake_redis.clear_admin_messages = AsyncMock()

    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="edit_message_text", message="bad request")

    fake_bot.edit_message_text = AsyncMock(side_effect=raise_bad_request)
    monkeypatch.setattr(
        "bot.utils.start_stop_bot.logger", fake_logger
    )  # замени module_name

    await start_module.edit_admin_messages(
        bot=fake_bot, user_id=10, new_text="Тест", redis_manager=fake_redis
    )

    fake_logger.warning.assert_called_once()
    fake_redis.clear_admin_messages.assert_awaited_once_with(10)
