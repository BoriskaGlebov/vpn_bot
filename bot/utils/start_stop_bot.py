from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from bot.config import bot, logger, settings_bot
from bot.redis_manager import SettingsRedis
from bot.utils.commands import set_bot_commands
from bot.utils.set_description_file import set_description


async def send_to_admins(
    bot: Bot,
    message_text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    telegram_id: Optional[int] = None,
    redis_manager: Optional[SettingsRedis] = None,
) -> None:
    """Отправляет сообщение всем администраторам с возможной inline-клавиатурой.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        redis_manager (SettingsRedis): хранение сообщений админа для дальнейшего изменения
        message_text (str): Текст сообщения для отправки администраторам.
        reply_markup (Optional[InlineKeyboardMarkup], optional): Inline-клавиатура для сообщения.
            По умолчанию None.
        telegram_id ( Optional[int]): Идентификатор пользователя от которого обновления.

    Returns
        None

    Raises
        TelegramBadRequest: Исключение логируется для каждого администратора,
            у которого не удалось отправить сообщение.

    """
    for admin_id in settings_bot.ADMIN_IDS:
        try:
            mes: Message = await bot.send_message(
                chat_id=admin_id, text=message_text, reply_markup=reply_markup
            )
            if telegram_id and redis_manager:
                await redis_manager.save_admin_message(
                    user_id=telegram_id, admin_id=admin_id, message_id=mes.message_id
                )
        except TelegramBadRequest as e:
            logger.bind(user=admin_id).error(
                f"Не удалось отправить сообщение админу {admin_id}: {e}"
            )
            continue


async def edit_admin_messages(
    bot: Bot,
    user_id: int,
    new_text: str,
    redis_manager: SettingsRedis,
) -> None:
    """Редактирует все сообщения администраторов, относящиеся к конкретному пользователю.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        user_id (int): Telegram ID пользователя, к которому относятся сообщения.
        redis_manager (SettingsRedis): хранение сообщений админа для дальнейшего изменения
        new_text (str): Новый текст для сообщений админов.

    Returns
        None

    """
    admin_messages = await redis_manager.get_admin_messages(user_id)
    for msg in admin_messages:
        try:
            await bot.edit_message_text(
                chat_id=msg["chat_id"], message_id=msg["message_id"], text=new_text
            )
        except TelegramBadRequest:
            logger.warning(
                f"Не удалось отредактировать сообщение {msg['chat_id']}:{msg['message_id']}"
            )
            continue

    await redis_manager.clear_admin_messages(user_id)


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
