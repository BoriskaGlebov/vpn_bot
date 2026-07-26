from aiogram import Bot

from bot.core.config import settings_bot
from bot.help.utils.common_device import Device


class SplitDevice(Device):
    """Отправляет пользователю инструкции по настройке раздельного туннелирования."""

    PREFIX = f"{settings_bot.bucket.prefix}amnezia_split/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.split
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.split
    CAPTION_SLEEP = 1.2

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет инструкции по раздельному туннелированию.

        Формат: вступительное сообщение со ссылкой на приложение
        (`{link}` в тексте), затем серия фото-инструкций с подписями
        (тоже могут содержать `{link}`), финальное сообщение без ссылки.

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
            intro_formatter=lambda text: text.format(link=link),
            caption_formatter=lambda text: text.format(link=link),
            final_formatter=lambda text: text,
        )
