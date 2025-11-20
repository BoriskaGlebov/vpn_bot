import asyncio
from itertools import zip_longest

from aiogram import Bot
from aiogram.types import FSInputFile

from bot.config import settings_bot
from bot.help.utils.common_device import Device


class AndroidDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Android."""

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю инструкцию по настройке VPN на Android.

        Метод отправляет серию изображений с подписями, взятыми из конфигурации
        `settings_bot.MESSAGES["modes"]["help"]["instructions"]["android"]`.
        Каждое изображение соответствует шагу инструкции по настройке VPN на Android.

        Args:
            bot (Bot): Экземпляр бота Aiogram, используемый для отправки сообщений.
            chat_id (int): Идентификатор чата Telegram, куда будут отправлены инструкции.

        Raises
            FileNotFoundError: Если директория с медиафайлами не найдена.
            TelegramAPIError: Если при отправке сообщений возникает ошибка Telegram API.

        """
        media = settings_bot.BASE_DIR / "bot" / "help" / "media" / "amnezia_android"
        m_android = settings_bot.MESSAGES["modes"]["help"]["instructions"]["android"]
        if not media.exists():
            raise FileNotFoundError(media)
        for file, answertext in zip_longest(sorted(media.iterdir()), m_android):
            await bot.send_photo(
                chat_id=chat_id,
                caption=answertext if answertext else None,
                photo=FSInputFile(file),
                show_caption_above_media=True,
            )
            await asyncio.sleep(1)
