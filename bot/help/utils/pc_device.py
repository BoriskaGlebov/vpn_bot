from bot.core.config import settings_bot
from bot.help.utils.common_device import Device


class PCDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для ПК."""

    PREFIX = f"{settings_bot.bucket.prefix}amnezia_pc/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.pc
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.pc
