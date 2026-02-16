import asyncio
from itertools import zip_longest

from aiogram import Bot

from bot.config import settings_bot, settings_bucket
from bot.help.keyboards.inline_kb import send_link_button
from bot.help.utils.common_device import Device


class IphoneDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для iPhone."""

    PREFIX = f"{settings_bucket.prefix}amnezia_iphone/"

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю инструкцию по настройке VPN на iPhone.

        Метод отправляет серию изображений с подписями, взятыми из настроек
        `settings_bot.messages.modes.help.instructions.iphone`.
        Каждое изображение соответствует одному шагу инструкции.

        Args:
            bot (Bot): Экземпляр бота Aiogram, через который выполняется отправка сообщений.
            chat_id (int): Идентификатор чата Telegram, куда будут отправлены сообщения.

        Raises
            FileNotFoundError: Если директория с медиафайлами не найдена.
            TelegramAPIError: Если при отправке сообщения возникает ошибка Telegram API.

        """
        media = await cls._list_files()
        m_iphone = settings_bot.messages.modes.help.instructions.iphone
        link = settings_bot.messages.modes.help.instructions.links.iphone
        for file, answertext in zip_longest(media, m_iphone):
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
