from aiogram import Bot

from bot.core.config import settings_bot
from bot.help.utils.common_device import Device


class IncyDevice(Device):
    """Класс получения инструкции по настройке клиента INCY."""

    PREFIX = f"{settings_bot.bucket.prefix}incy/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.incy
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.incy
    CAPTION_SLEEP = 1.2

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет инструкции по настройке INCY.

        Формат: вступительное сообщение со ссылками на приложение под
        разные ОС (именованные `{android}`/`{ios}`/`{windows}`/`{linux}`,
        подставляются из `LINK_PATH`), затем серия фото-инструкций без
        ссылок, финальное сообщение снова со ссылками — чтобы не заставлять
        пользователя отматывать чат к началу инструкции.

        Args:
            bot (Bot): Экземпляр бота Aiogram.
            chat_id (int): Telegram chat_id пользователя.

        Raises
            DeviceEmptyMessagesError: если для устройства не заданы подписи.
            DeviceEmptyMediaError: если в S3 не найдено ни одного файла.
            DeviceInstructionMismatchError: если количество подписей не
                соответствует количеству файлов.
            TelegramAPIError: при ошибке отправки сообщения в Telegram.

        """
        links = cls.LINK_PATH
        # `final_formatter` не передаём: по умолчанию он совпадает с
        # `intro_formatter`, а финалу нужны те же ссылки.
        await cls._send_intro_media_final(
            bot,
            chat_id,
            intro_formatter=lambda text: text.format(**links),
        )
