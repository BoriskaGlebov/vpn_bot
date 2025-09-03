from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot.config import (
    bot,
    logger,
    settings_bot,
)

# Команды для обычных пользователей
user_commands: list[BotCommand] = [
    BotCommand(command=command, description=description)
    for command, description in settings_bot.MESSAGES["commands"]["users"].items()
]

# Команды для администраторов
admin_commands: list[BotCommand] = [
    BotCommand(command=command, description=description)
    for command, description in settings_bot.MESSAGES["commands"]["admins"].items()
]


@logger.catch  # type: ignore[misc]
async def set_bot_commands() -> None:
    """Устанавливает команды для пользователей и администраторов.

     - Обычные пользователи получают стандартный набор команд.
     - Администраторы получают дополнительные команды.
    Returns: None.

    """
    # Устанавливаем команды по умолчанию для всех (обычные пользователи)
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    # Устанавливаем команды для администраторов
    for admin_id in settings_bot.ADMIN_IDS:
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
