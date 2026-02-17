import asyncio

from aiogram import Bot

from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class SplitDevice(Device):
    """Отправляет пользователю инструкции по настройке раздельного туннелирования."""

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

        if not messages:
            raise ValueError(f"{cls.__name__}: Пустой список инстуркций")

        if not media:
            raise ValueError(f"{cls.__name__}: Нет файлов в  S3")

        if len(messages) < 1:
            raise ValueError(
                f"{cls.__name__}: сообщения должны содержать хотя бы 1 элемент"
            )

        if len(messages) not in {len(media), len(media) + 1, len(media) + 2}:
            raise ValueError(
                f"{cls.__name__}: media({len(media)}) and messages({len(messages)}) Неподходит"
            )

        await bot.send_message(chat_id, messages[0], disable_web_page_preview=True)
        for file, caption in zip(media, messages[1:]):
            await bot.send_photo(chat_id=chat_id, photo=file, caption=caption)
            await asyncio.sleep(1.5)
        if (len(messages) - len(media)) > 1:
            await bot.send_message(chat_id, messages[-1])
