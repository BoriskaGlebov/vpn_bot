import asyncio

from aiogram import Bot

from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class SplitDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Android."""

    PREFIX = f"{settings_bucket.prefix}amnezia_split/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.split
    LINK_PATH = None

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет сообщение в указанный чат.

        Этот метод должен быть реализован в подклассах для отправки
        определённого типа сообщения (текста, фото, видео и т.д.) с помощью
        экземпляра бота Aiogram.

        Args:
            bot (Bot): Экземпляр бота Aiogram, используемый для отправки сообщения.
            chat_id (int): Идентификатор чата Telegram, куда будет отправлено сообщение.

        Raises
            TelegramAPIError: Если при взаимодействии с Telegram API возникает ошибка.

        """
        media = await cls._list_files()
        messages = cls.MESSAGES_PATH
        await bot.send_message(chat_id, messages[0], disable_web_page_preview=True)
        for file, caption in zip(media, messages[1:]):
            await bot.send_photo(chat_id=chat_id, photo=file, caption=caption)
            await asyncio.sleep(1.5)
        if (len(messages) - len(media)) > 1:
            await bot.send_message(chat_id, messages[-1])
