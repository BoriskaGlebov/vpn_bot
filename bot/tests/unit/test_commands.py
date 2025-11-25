from unittest.mock import ANY

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.utils import commands


@pytest.mark.asyncio
@pytest.mark.utils
async def test_set_bot_commands_success(patch_deps, fake_bot, fake_logger):
    fake_bot.set_my_commands.return_value = None
    # act
    await commands.set_bot_commands()
    # assert
    fake_bot.set_my_commands.assert_any_call(commands.user_commands, scope=ANY)
    fake_bot.set_my_commands.assert_any_call(commands.group_commands, scope=ANY)
    fake_bot.set_my_commands.assert_any_call(commands.admin_commands, scope=ANY)
    for call in fake_bot.set_my_commands.call_args_list[1:]:
        args, kwargs = call
        assert args[0] in (
            commands.group_commands,
            commands.admin_commands,
            commands.user_commands,
        )
    fake_logger.error.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.utils
async def test_set_bot_commands_admin_chat_not_found_logs_error(
    patch_deps, fake_bot, fake_logger
):
    async def side_effect(*args, **kwargs):
        if args and args[0] == commands.admin_commands:
            raise TelegramBadRequest(
                method="set_bot_commands", message="chat not found"
            )
        return None

    fake_bot.set_my_commands.side_effect = side_effect

    # act
    await commands.set_bot_commands()

    # assert
    fake_bot.set_my_commands.assert_any_call(commands.user_commands, scope=ANY)
    fake_logger.error.assert_called()
    msg = fake_logger.error.call_args[0][0]
    assert "не начат чат с ботом" in msg


@pytest.mark.parametrize(
    "admin_ids",
    [
        [123, 456],
        [*[num for num in range(100)], 456],
    ],
)
@pytest.mark.asyncio
@pytest.mark.utils
async def test_set_bot_commands_other_telegram_error_raises(
    patch_deps, fake_bot, fake_logger, monkeypatch, admin_ids
):
    async def side_effect(*args, **kwargs):
        if args and args[0] == commands.admin_commands:
            chat_id = kwargs["scope"].chat_id
            if chat_id == 456:
                raise TelegramBadRequest(
                    method="set_bot_commands", message="some other error"
                )

        return None

    fake_bot.set_my_commands.side_effect = side_effect
    monkeypatch.setattr(commands.settings_bot, "ADMIN_IDS", admin_ids)
    # act
    with pytest.raises(TelegramBadRequest):
        await commands.set_bot_commands()
    # assert
    fake_logger.error.assert_not_called()
