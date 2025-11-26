from aiogram import Bot

from bot.help.utils.common_device import Device


class PCDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для ПК."""

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        pass
