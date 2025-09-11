import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetMyCommands, GetMyDescription

from bot.main import start_bot, stop_bot


@pytest.mark.asyncio
@pytest.mark.integration
async def test_start_and_stop(test_bot):
    bot, admin_id, test_settings = test_bot

    try:
        await start_bot()
    except TelegramBadRequest as e:
        pytest.fail(f"start_bot() вызвал ошибку при работе с Telegram API: {e}")

    commands_response = await bot(GetMyCommands())
    commands_texts = [cmd.command for cmd in commands_response]
    assert len(commands_texts) > 0, "Команды не были установлены"
    assert commands_texts == list(
        test_settings.MESSAGES["commands"]["users"].keys()
    ), "Команды не соответствуют ожидаемым"

    description_response = await bot(GetMyDescription())
    description_text = description_response.description
    assert description_text, "Описание бота не установлено"
    assert (
        test_settings.MESSAGES["description"].strip() in description_text
    ), "Описание бота не соответствует ожидаемому"

    try:
        await stop_bot()
    except TelegramBadRequest as e:
        pytest.fail(f"stop_bot() вызвал ошибку при работе TelegramApi: {e}")
