import asyncio
from itertools import zip_longest

from aiogram import Bot

from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class AndroidDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Android."""

    PREFIX = f"{settings_bucket.prefix}amnezia_android/"

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю инструкцию по настройке VPN на Android.

        Метод отправляет серию изображений с подписями, взятыми из конфигурации
        `settings_bot.messages.modes.help.instructions.android`.
        Каждое изображение соответствует шагу инструкции по настройке VPN на Android.

        Args:
            bot (Bot): Экземпляр бота Aiogram, используемый для отправки сообщений.
            chat_id (int): Идентификатор чата Telegram, куда будут отправлены инструкции.

        Raises
            FileNotFoundError: Если директория с медиафайлами не найдена.
            TelegramAPIError: Если при отправке сообщений возникает ошибка Telegram API.

        """
        media = await cls._list_files()
        m_android = settings_bot.messages.modes.help.instructions.android
        for file, answertext in zip_longest(media, m_android):
            await bot.send_photo(
                chat_id=chat_id,
                caption=answertext if answertext else None,
                photo=file,
                show_caption_above_media=True,
            )
            await asyncio.sleep(1)
