from aiogram import Bot

from bot.core.config import settings_bot
from bot.help.keyboards.inline_kb import android_download_kb
from bot.help.utils.common_device import Device


class AndroidDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Android."""

    PREFIX = f"{settings_bot.bucket.prefix}amnezia_android/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.android
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.android
    APK_PATH = settings_bot.messages.modes.help.instructions.android_apk

    @classmethod
    async def _send_download_block(cls, bot: Bot, chat_id: int, link: str) -> None:
        """Отправляет выбор способа установки: Google Play или прямой APK.

        В отличие от базовой реализации даёт запасной путь тем, у кого
        Google Play недоступен: кнопка «Скачать APK напрямую» ведёт в
        пошаговый выбор файла (хендлеры `apk_*` в `bot/help/router.py`).

        Args:
            bot (Bot): Экземпляр aiogram-бота.
            chat_id (int): Telegram chat_id пользователя.
            link (str): Ссылка на приложение в Google Play.

        Raises
            TelegramAPIError: при ошибке отправки сообщения в Telegram.

        """
        await bot.send_message(
            chat_id=chat_id,
            text=cls.APK_PATH.choose,
            reply_markup=android_download_kb(link),
        )
