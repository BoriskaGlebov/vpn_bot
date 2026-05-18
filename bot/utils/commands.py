import asyncio

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from bot.core.config import (
    bot,
    logger,
    settings_bot,
)

# Команды для обычных пользователей
user_commands: list[BotCommand] = [
    BotCommand(command=command, description=description)
    for command, description in settings_bot.messages.commands.users.items()
]

# Команды для администраторов
admin_commands: list[BotCommand] = [
    BotCommand(command=command, description=description)
    for command, description in settings_bot.messages.commands.admins.items()
]
group_commands = [
    BotCommand(command=command, description=description)
    for command, description in settings_bot.messages.commands.group.items()
]


async def set_bot_commands() -> None:
    """Устанавливает команды для пользователей и администраторов.

     - Обычные пользователи получают стандартный набор команд.
     - Администраторы получают дополнительные команды.
    Returns: None.

    """
    all_scopes = (
        BotCommandScopeDefault(),
        BotCommandScopeAllPrivateChats(),
        BotCommandScopeAllGroupChats(),
        BotCommandScopeAllChatAdministrators(),
    )
    for scope in all_scopes:
        try:
            await bot.delete_my_commands(scope=scope)
            logger.info(f"Очищен {scope.__class__.__name__}")
        except Exception as e:
            logger.error(f"Ошибка {scope.__class__.__name__}: {e}")
    await asyncio.sleep(1)

    for scope in all_scopes:
        cmds = await bot.get_my_commands(scope=scope)
        logger.info(f"{scope.__class__.__name__}: {[c.command for c in cmds]}")

    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())

    for admin_id in settings_bot.core.admin_ids:
        try:
            await bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except TelegramBadRequest as e:
            if "chat not found" in str(e):
                logger.bind(user=admin_id).error(
                    f"⚠️  Ошибка: у администратора {admin_id} не начат чат с ботом."
                )
            else:
                raise
