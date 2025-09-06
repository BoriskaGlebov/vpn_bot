from unittest.mock import ANY, AsyncMock

import pytest

from bot.config import settings_bot
from bot.help.router import help_cmd
from bot.utils.commands import admin_commands, user_commands


@pytest.mark.asyncio
@pytest.mark.help
async def test_help_cmd_for_admin(monkeypatch):
    # Подготовка фиктивного сообщения и состояния
    message = AsyncMock()
    message.from_user.id = 123
    state = AsyncMock()

    # Подменяем список админов
    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123])
    monkeypatch.setattr(
        settings_bot, "MESSAGES", {"general": {"common_error": "Ошибка"}}
    )

    # Вызов корутины
    await help_cmd(message, state)

    # Проверяем, что state.clear был вызван
    state.clear.assert_awaited_once()

    # Проверяем, что message.answer вызван с командами админа
    expected_text = "\n".join(
        f"/{cmd.command} - {cmd.description}" for cmd in admin_commands
    )
    message.answer.assert_awaited_once_with(text=expected_text, reply_markup=ANY)


@pytest.mark.asyncio
@pytest.mark.help
async def test_help_cmd_for_user(monkeypatch, fake_logger):
    message = AsyncMock()
    message.from_user.id = 999
    state = AsyncMock()

    # Подменяем список админов
    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123])
    monkeypatch.setattr(
        settings_bot, "MESSAGES", {"general": {"common_error": "Ошибка"}}
    )

    await help_cmd(message, state)

    state.clear.assert_awaited_once()

    expected_text = "\n".join(
        f"/{cmd.command} - {cmd.description}" for cmd in user_commands
    )
    message.answer.assert_awaited_once_with(text=expected_text, reply_markup=ANY)


@pytest.mark.asyncio
@pytest.mark.help
async def test_help_cmd_handles_exception(monkeypatch, fake_logger):
    # Создаём моки
    message = AsyncMock()
    message.from_user.id = 123
    state = AsyncMock()
    state.clear.return_value = AsyncMock()

    # Настраиваем тестовые данные
    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123])
    monkeypatch.setattr(
        settings_bot, "MESSAGES", {"general": {"common_error": "Ошибка"}}
    )

    monkeypatch.setattr("bot.help.router.logger", fake_logger)

    # force Exception в message.answer для проверки блока except
    call_count = 0

    async def answer_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("fail")  # первый вызов бросает исключение
        return None  # второй вызов успешный

    message.answer.side_effect = answer_side_effect

    # Запускаем корутину
    await help_cmd(message, state)

    # Проверяем, что state.clear был вызван
    state.clear.assert_awaited_once()

    # Проверяем, что логгер отработал
    fake_logger.error.assert_called_once()
    logged_msg = fake_logger.error.call_args[0][0]
    assert "Ошибка при выполнении команды /help" in logged_msg

    # Проверяем, что message.answer был вызван дважды
    assert message.answer.await_count == 2
    # Второй вызов должен содержать текст ошибки
    assert message.answer.await_args_list[1].args[0] == "Ошибка"
