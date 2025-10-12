import asyncio
from itertools import zip_longest

from aiogram import Bot
from aiogram.types import FSInputFile
from config import settings_bot

from bot.help.utils.common_device import Device


class TVDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Smart TV."""

    @classmethod
    async def send_message(self, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю инструкцию по настройке VPN на Smart TV.

        Метод последовательно отправляет изображения с подписями,
        соответствующими шагам инструкции, взятым из настроек
        `settings_bot.MESSAGES["modes"]["help"]["instructions"]["tv"]`.

        Args:
            bot (Bot): Экземпляр бота Aiogram, используемый для отправки сообщений.
            chat_id (int): Идентификатор чата Telegram, куда будут отправлены инструкции.

        Raises
            FileNotFoundError: Если директория с медиафайлами не найдена.
            TelegramAPIError: Если при отправке сообщений возникает ошибка Telegram API.

        """
        media = settings_bot.BASE_DIR / "bot" / "help" / "media" / "amnezia_wg"
        m_tv = settings_bot.MESSAGES["modes"]["help"]["instructions"]["tv"]
        if not media.exists():
            raise FileNotFoundError(media)
        for file, answertext in zip_longest(sorted(media.iterdir()), m_tv):
            await bot.send_photo(
                chat_id=chat_id,
                caption=answertext if answertext else None,
                photo=FSInputFile(file),
                show_caption_above_media=True,
            )
            await asyncio.sleep(1)
