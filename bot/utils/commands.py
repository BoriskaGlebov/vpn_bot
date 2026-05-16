from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
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
    logger.info("Удаляю старые команды пользователям.")
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
    await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code="en")

    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())

    for admin_id in settings_bot.core.admin_ids:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
    logger.success(
        "Удалил старые команды для пользователей.Устанавливаю новые команды."
    )
    # Временные команды
    await bot.set_my_commands(
        [BotCommand(command="reset", description="reset")],
        scope=BotCommandScopeDefault(),
    )
    #
    # await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    #
    # # await bot.set_my_commands(user_commands, scope=BotCommandScopeAllPrivateChats())
    # await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    #
    # for admin_id in settings_bot.core.admin_ids:
    #     try:
    #         await bot.set_my_commands(
    #             admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
    #         )
    #     except TelegramBadRequest as e:
    #         if "chat not found" in str(e):
    #             logger.bind(user=admin_id).error(
    #                 f"⚠️  Ошибка: у администратора {admin_id} не начат чат с ботом."
    #             )
    #         else:
    #             raise
    #
    # commands = await bot.get_my_commands(scope=BotCommandScopeAllPrivateChats())
    #
    # logger.info(commands)
    #
    # commands = await bot.get_my_commands(scope=BotCommandScopeDefault())
    #
    # logger.info(commands)
