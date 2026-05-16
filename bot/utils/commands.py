import asyncio

from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
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
    # 1. Очищаем все скоупы подряд (несколько раз для надежности)
    all_scopes = [
        BotCommandScopeDefault(),
        BotCommandScopeAllPrivateChats(),
        BotCommandScopeAllGroupChats(),
        BotCommandScopeAllChatAdministrators(),
    ]

    for _ in range(3):  # Повторяем 3 раза
        for scope in all_scopes:
            try:
                await bot.delete_my_commands(scope=scope)
                logger.info(f"Очищен {scope.__class__.__name__}")
            except Exception as e:
                logger.error(f"Ошибка {scope.__class__.__name__}: {e}")
        await asyncio.sleep(1)

    # 2. Проверяем результат
    for scope in all_scopes:
        cmds = await bot.get_my_commands(scope=scope)
        logger.info(f"{scope.__class__.__name__}: {[c.command for c in cmds]}")

    # 3. Теперь устанавливаем ТОЛЬКО в Default
    await bot.set_my_commands(
        [BotCommand(command="reset", description="reset")],
        scope=BotCommandScopeDefault(),
    )

    # 4. Финальная проверка
    final = await bot.get_my_commands()
    logger.success(f"✅ Финальные команды в Default: {[c.command for c in final]}")
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
