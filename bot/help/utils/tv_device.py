import asyncio
from itertools import zip_longest

from aiogram import Bot

from bot.config import settings_bot, settings_bucket
from bot.help.keyboards.inline_kb import send_link_button
from bot.help.utils.common_device import Device


class TVDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Smart TV."""

    PREFIX = f"{settings_bucket.prefix}amnezia_wg/"

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
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
        media = await cls._list_files()
        m_tv = settings_bot.messages.modes.help.instructions.tv
        link = settings_bot.messages.modes.help.instructions.links.tv
        for file, answertext in zip_longest(media, m_tv):
            await bot.send_photo(
                chat_id=chat_id,
                caption=answertext if answertext else None,
                photo=file,
                show_caption_above_media=True,
            )
            await asyncio.sleep(1)
        if link:
            await send_link_button(
                bot=bot,
                chat_id=chat_id,
                text="Скачайте приложение по ссылке:",
                url=link,
            )
