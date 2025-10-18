from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from bot.config import bot, logger, settings_bot
from bot.utils.commands import set_bot_commands
from bot.utils.set_description_file import set_description


async def send_to_admins(
    bot: Bot, message_text: str, reply_markup: Optional[InlineKeyboardMarkup] = None
) -> None:
    """Отправляет сообщение всем администраторам с возможной inline-клавиатурой.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        message_text (str): Текст сообщения для отправки администраторам.
        reply_markup (Optional[InlineKeyboardMarkup], optional): Inline-клавиатура для сообщения.
            По умолчанию None.

    Returns
        None

    Raises
        TelegramBadRequest: Исключение логируется для каждого администратора,
            у которого не удалось отправить сообщение.

    """
    for admin_id in settings_bot.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id, text=message_text, reply_markup=reply_markup
            )
        except TelegramBadRequest as e:
            logger.bind(user=admin_id).error(
                f"Не удалось отправить сообщение админу {admin_id}: {e}"
            )
            continue


async def start_bot() -> None:
    """Инициализация и запуск бота.

    Эта функция устанавливает команды для бота с помощью `set_commands()`,
    устанавливает описание с помощью `set_description()`,
    а также отправляет сообщение администраторам, информируя их о запуске бота.
    """
    await set_bot_commands()
    await set_description(bot=bot)
    await send_to_admins(bot=bot, message_text="Я запущен🥳.")
    logger.info("Бот успешно запущен.")


async def stop_bot() -> None:
    """Остановка бота.

    Эта функция отправляет сообщение администраторам, уведомляя их о том,
    что бот был остановлен, и логирует это событие.
    """
    await send_to_admins(bot=bot, message_text="Бот остановлен. За что?😔")
    logger.error("Бот остановлен!")
