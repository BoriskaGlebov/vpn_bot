from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from bot.app_error.base_error import MessageNotFoundError
from bot.core.config import logger, settings_bot
from bot.redis_service import RedisAdminMessageStorage
from bot.utils.commands import set_bot_commands
from bot.utils.set_description_file import set_description


async def send_to_admins(
    bot: Bot,
    message_text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    telegram_id: int | None = None,
    admin_mess_storage: RedisAdminMessageStorage | None = None,
) -> None:
    """Отправляет сообщение всем администраторам с возможной inline-клавиатурой.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        admin_mess_storage (RedisAdminMessageStorage ): хранение сообщений админа для дальнейшего изменения
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
    for admin_id in settings_bot.admin_ids:
        try:
            mes: Message = await bot.send_message(
                chat_id=admin_id, text=message_text, reply_markup=reply_markup
            )
            if telegram_id and admin_mess_storage:
                await admin_mess_storage.add(
                    user_id=telegram_id, admin_id=admin_id, message_id=mes.message_id
                )
            logger.info("Отправлено сообщение Админу")
        except TelegramBadRequest as e:
            logger.bind(user=admin_id).error(
                f"Не удалось отправить сообщение админу {admin_id}: {e}"
            )
            continue


async def edit_admin_messages(
    bot: Bot,
    user_id: int,
    new_text: str,
    admin_mess_storage: RedisAdminMessageStorage,
) -> None:
    """Редактирует все сообщения администраторов, относящиеся к конкретному пользователю.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        user_id (int): Telegram ID пользователя, к которому относятся сообщения.
        admin_mess_storage (RedisAdminMessageStorage): хранение сообщений админа для дальнейшего изменения
        new_text (str): Новый текст для сообщений админов.

    Returns
        None

    """
    admin_messages = await admin_mess_storage.get(user_id)
    if admin_messages:
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
    else:
        raise MessageNotFoundError(message="Ненайдено сообщение для редактирования.")

    await admin_mess_storage.clear(user_id)


async def start_bot(bot: Bot) -> None:
    """Инициализация и запуск бота.

    Эта функция устанавливает команды для бота с помощью `set_commands()`,
    устанавливает описание с помощью `set_description()`,
    а также отправляет сообщение администраторам, информируя их о запуске бота.

    Args:
        bot (Bot): Экземпляр бота Aiogram.

    """
    await set_bot_commands()
    await set_description(bot=bot)
    await send_to_admins(bot=bot, message_text="Я запущен🥳.")
    logger.info("Бот успешно запущен.")


async def stop_bot(bot: Bot) -> None:
    """Остановка бота.

    Эта функция отправляет сообщение администраторам, уведомляя их о том,
    что бот был остановлен, и логирует это событие.

    Args:
        bot (Bot): Экземпляр бота Aiogram.

    """
    await send_to_admins(bot=bot, message_text="Бот остановлен. За что?😔")
    logger.error("Бот остановлен!")
