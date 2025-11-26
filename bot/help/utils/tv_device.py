from aiogram import Bot

from bot.help.utils.common_device import Device


class TVDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Smart TV."""

    @classmethod
    async def send_message(self, bot: Bot, chat_id: int) -> None:
        pass
