import asyncio
from itertools import zip_longest

from aiogram import Bot
from aiogram.types import FSInputFile
from config import settings_bot

from bot.help.utils.common_device import Device


class IphoneDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для iPhone."""

    @classmethod
    async def send_message(self, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю инструкцию по настройке VPN на iPhone.

        Метод отправляет серию изображений с подписями, взятыми из настроек
        `settings_bot.MESSAGES["modes"]["help"]["instructions"]["iphone"]`.
        Каждое изображение соответствует одному шагу инструкции.

        Args:
            bot (Bot): Экземпляр бота Aiogram, через который выполняется отправка сообщений.
            chat_id (int): Идентификатор чата Telegram, куда будут отправлены сообщения.

        Raises
            FileNotFoundError: Если директория с медиафайлами не найдена.
            TelegramAPIError: Если при отправке сообщения возникает ошибка Telegram API.

        """
        media = settings_bot.BASE_DIR / "bot" / "help" / "media" / "amnezia_iphone"
        m_iphone = settings_bot.MESSAGES["modes"]["help"]["instructions"]["iphone"]
        if not media.exists():
            raise FileNotFoundError(media)
        for file, answertext in zip_longest(sorted(media.iterdir()), m_iphone):
            await bot.send_photo(
                chat_id=chat_id,
                caption=answertext if answertext else None,
                photo=FSInputFile(file),
                show_caption_above_media=True,
            )
            await asyncio.sleep(1)


#
# if __name__ == '__main__':
#     dirrr = settings_bot.BASE_DIR / "bot" / "help" / "media" / "amnezia_android"
#     # print(list(dirrr.iterdir()))
#     for file in sorted(dirrr.iterdir()):
#         print(file)
