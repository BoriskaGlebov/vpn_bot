from aiogram import Bot

from bot.core.config import settings_bot
from bot.help.utils.common_device import Device


class HappDevice(Device):
    """Класс получения инструкции настройки Happ."""

    PREFIX = f"{settings_bot.bucket.prefix}happ/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.happ
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.happ
    CAPTION_SLEEP = 1.2

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет инструкции по настройке Happ.

        Формат: вступительное сообщение с набором ссылок под разные ОС
        (позиционные `{}`-плейсхолдеры, подставляются из списка `LINK_PATH`),
        затем серия фото-инструкций без ссылок, финальное сообщение снова
        со ссылками.

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
        link = cls.LINK_PATH
        await cls._send_intro_media_final(
            bot,
            chat_id,
            intro_formatter=lambda text: text.format(*link),
            final_formatter=lambda text: text.format(*link),
        )
