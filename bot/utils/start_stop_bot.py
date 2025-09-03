from aiogram.exceptions import TelegramBadRequest

from bot.config import bot, logger, settings_bot
from bot.utils.commands import set_bot_commands
from bot.utils.set_description_file import set_description


@logger.catch  # type: ignore[misc]
async def start_bot() -> None:
    """Инициализация и запуск бота.

    Эта функция устанавливает команды для бота с помощью `set_commands()`,
    устанавливает описание с помощью `set_description()`,
    а также отправляет сообщение администраторам, информируя их о запуске бота.
    """
    await set_bot_commands()
    await set_description(bot=bot)
    for admin_id in settings_bot.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "Я запущен🥳.")
        except TelegramBadRequest as e:
            logger.bind(user=admin_id).error(
                f"Не удалось отправить сообщение админу {admin_id}: {e}"
            )
            # pass
    logger.info("Бот успешно запущен.")


@logger.catch  # type: ignore[misc]
async def stop_bot() -> None:
    """Остановка бота.

    Эта функция отправляет сообщение администраторам, уведомляя их о том,
    что бот был остановлен, и логирует это событие.
    """
    for admin_id in settings_bot.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "Бот остановлен. За что?😔")
        except TelegramBadRequest as e:
            logger.bind(user=admin_id).error(
                f"Не удалось отправить сообщение админу {admin_id} об остановке бота: {e}"
            )
            # pass
    logger.error("Бот остановлен!")
