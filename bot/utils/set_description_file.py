from aiogram import Bot

from bot.config import settings_bot


async def set_description(bot: Bot) -> None:
    """Устанавливает описание бота в Telegram.

    Эта функция получает информацию о боте и устанавливает описание,
    которое включает имя бота и краткое объяснение его функционала.

    Args:
        bot (Bot): Экземпляр бота из aiogram.

    """
    inf = await bot.get_me()
    await bot.set_my_description(
        description=settings_bot.messages.description.format(bot_name=inf.first_name)
    )
