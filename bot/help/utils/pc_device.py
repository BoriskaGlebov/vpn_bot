import asyncio
from itertools import zip_longest

from aiogram import Bot

from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class PCDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для ПК."""

    PREFIX = f"{settings_bucket.prefix}amnezia_pc/"

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю инструкцию по настройке VPN на ПК.

        Метод поочерёдно отправляет изображения с поясняющими подписями,
        полученными из конфигурации `settings_bot.MESSAGES["modes"]["help"]["instructions"]["pc"]`.
        Каждое изображение соответствует шагу настройки VPN на компьютере.

        Args:
            bot (Bot): Экземпляр бота Aiogram, используемый для отправки сообщений.
            chat_id (int): Идентификатор чата Telegram, куда будут отправлены инструкции.

        Raises
            FileNotFoundError: Если директория с медиафайлами не найдена.
            TelegramAPIError: Если при отправке сообщений возникает ошибка Telegram API.

        """
        media = await cls._list_files()
        m_pc = settings_bot.messages["modes"]["help"]["instructions"]["pc"]
        for file, answertext in zip_longest(media, m_pc):
            await bot.send_photo(
                chat_id=chat_id,
                caption=answertext if answertext else None,
                photo=file,
                show_caption_above_media=True,
            )
            await asyncio.sleep(1)
