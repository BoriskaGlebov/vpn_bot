from aiogram import Bot

from bot.help.utils.common_device import Device


class IphoneDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для iPhone."""

    @classmethod
    async def send_message(self, bot: Bot, chat_id: int) -> None:
        pass
