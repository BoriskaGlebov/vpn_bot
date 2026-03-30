from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

import bot.core.config as config
from bot.utils import start_stop_bot as start_module


@pytest.mark.asyncio
@pytest.mark.utils
async def test_start_bot_sends_messages_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot: AsyncMock,
    fake_logger: AsyncMock,
) -> None:
    """Проверяет успешный запуск бота.

    Кейс:
    - вызываются set_bot_commands, set_description
    - отправляется сообщение админам
    - логируется успешный запуск
    """
    monkeypatch.setattr(start_module, "set_bot_commands", AsyncMock())
    monkeypatch.setattr(start_module, "set_description", AsyncMock())
    monkeypatch.setattr(start_module, "send_to_admins", AsyncMock())

    # Эмулируем частичную ошибку отправки (не должна ломать запуск)
    fake_bot.send_message = AsyncMock(
        side_effect=[None, TelegramBadRequest(method="send_message", message="ошибка")]
    )

    monkeypatch.setattr(start_module.settings_bot, "admin_ids", {111, 222})
    monkeypatch.setattr(start_module, "logger", fake_logger)

    # act
    await start_module.start_bot(bot=fake_bot)

    # assert
    start_module.set_bot_commands.assert_awaited_once()
    start_module.set_description.assert_awaited_once_with(bot=fake_bot)
    start_module.send_to_admins.assert_awaited_once_with(
        bot=fake_bot, message_text="Я запущен🥳."
    )
    fake_logger.info.assert_called_with("Бот успешно запущен.")


@pytest.mark.asyncio
@pytest.mark.utils
async def test_stop_bot_sends_messages_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot: AsyncMock,
    fake_logger: AsyncMock,
) -> None:
    """Проверяет корректную остановку бота.

    Кейс:
    - отправляется сообщение админам
    - логируется остановка
    """
    fake_bot.send_message = AsyncMock()
    fake_logger.bind.return_value = fake_logger

    monkeypatch.setattr(start_module.settings_bot, "admin_ids", {1, 2, 3})
    monkeypatch.setattr(start_module, "logger", fake_logger)
    monkeypatch.setattr(start_module, "send_to_admins", AsyncMock())

    # act
    await start_module.stop_bot(bot=fake_bot)

    # assert
    start_module.send_to_admins.assert_awaited_once_with(
        bot=fake_bot, message_text="Бот остановлен. За что?😔"
    )
    fake_logger.error.assert_any_call("Бот остановлен!")


@pytest.mark.asyncio
@pytest.mark.utils
async def test_send_to_admins_logs_bad_request(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot: AsyncMock,
    fake_logger: AsyncMock,
) -> None:
    """Проверяет логирование ошибки при отправке админу.

    Кейс:
    - send_message кидает TelegramBadRequest
    - ошибка ловится и логируется
    """

    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="send_message", message="bad request")

    fake_bot.send_message = AsyncMock(side_effect=raise_bad_request)
    fake_logger.bind.return_value = fake_logger

    monkeypatch.setattr(start_module.settings_bot, "admin_ids", {42})
    monkeypatch.setattr(start_module, "logger", fake_logger)

    # act
    await start_module.send_to_admins(
        bot=fake_bot,
        message_text="Бот остановлен. За что?😔",
    )

    # assert
    fake_logger.bind.assert_called_with(user=42)
    fake_logger.error.assert_called_once_with(
        "Не удалось отправить сообщение админу 42: Telegram server says - bad request"
    )


@pytest.mark.asyncio
@pytest.mark.utils
async def test_send_to_admins_success(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot: AsyncMock,
) -> None:
    """Проверяет успешную отправку сообщений всем админам.

    Кейс:
    - сообщение уходит каждому admin_id
    """
    fake_bot.send_message = AsyncMock()

    monkeypatch.setattr(start_module.settings_bot, "admin_ids", {1, 2})

    await start_module.send_to_admins(
        bot=fake_bot,
        message_text="Привет админы!",
    )

    assert fake_bot.send_message.await_count == 2
    fake_bot.send_message.assert_any_await(
        chat_id=1,
        text="Привет админы!",
        reply_markup=None,
    )
    fake_bot.send_message.assert_any_await(
        chat_id=2,
        text="Привет админы!",
        reply_markup=None,
    )


@pytest.mark.asyncio
@pytest.mark.utils
async def test_send_to_admins_handles_bad_request(
    monkeypatch: pytest.MonkeyPatch,
    fake_logger: AsyncMock,
    fake_bot: AsyncMock,
) -> None:
    """Дублирующий кейс: ошибка Telegram логируется и не падает.

    Кейс:
    - при ошибке отправки выполняется логирование
    - выполнение продолжается
    """

    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="send_message", message="bad request")

    fake_bot.send_message = AsyncMock(side_effect=raise_bad_request)

    monkeypatch.setattr("bot.utils.start_stop_bot.logger", fake_logger)
    monkeypatch.setattr(config.settings_bot, "admin_ids", {42})

    await start_module.send_to_admins(bot=fake_bot, message_text="Тест")

    assert fake_bot.send_message.await_count == 1
    fake_logger.bind.assert_called_with(user=42)
    fake_logger.error.assert_called_once_with(
        "Не удалось отправить сообщение админу 42: Telegram server says - bad request"
    )


@pytest.mark.asyncio
@pytest.mark.utils
async def test_edit_admin_messages_success(
    fake_bot: AsyncMock,
    fake_redis_service,
) -> None:
    """Проверяет редактирование сообщений админов.

    Кейс:
    - редактируются все сообщения из Redis
    - после этого записи очищаются
    """
    fake_redis_service.get = AsyncMock(
        return_value=[
            {"chat_id": 1, "message_id": 101},
            {"chat_id": 2, "message_id": 102},
        ]
    )

    await start_module.edit_admin_messages(
        bot=fake_bot,
        user_id=10,
        new_text="Новый текст",
        admin_mess_storage=fake_redis_service,
    )

    assert fake_bot.edit_message_text.await_count == 2
    fake_redis_service.clear.assert_awaited_once_with(10)


@pytest.mark.asyncio
@pytest.mark.utils
async def test_edit_admin_messages_handles_bad_request(
    monkeypatch: pytest.MonkeyPatch,
    fake_logger: AsyncMock,
    fake_bot: AsyncMock,
    fake_redis_service,
) -> None:
    """Проверяет обработку ошибки при редактировании сообщений.

    Кейс:
    - edit_message_text кидает TelegramBadRequest
    - ошибка логируется (warning)
    - Redis очищается в любом случае
    """
    fake_redis_service.get = AsyncMock(
        return_value=[
            {"chat_id": 1, "message_id": 101},
        ]
    )

    async def raise_bad_request(*args, **kwargs):
        raise TelegramBadRequest(method="edit_message_text", message="bad request")

    fake_bot.edit_message_text = AsyncMock(side_effect=raise_bad_request)

    monkeypatch.setattr("bot.utils.start_stop_bot.logger", fake_logger)

    await start_module.edit_admin_messages(
        bot=fake_bot,
        user_id=10,
        new_text="Тест",
        admin_mess_storage=fake_redis_service,
    )

    fake_logger.warning.assert_called_once()
    fake_redis_service.clear.assert_awaited_once_with(10)
