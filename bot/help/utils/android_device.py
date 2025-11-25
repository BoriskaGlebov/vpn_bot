from aiogram import Bot

from bot.help.utils.common_device import Device


class AndroidDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Android."""

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        pass
