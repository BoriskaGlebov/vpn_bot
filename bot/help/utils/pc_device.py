from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class PCDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для ПК."""

    PREFIX = f"{settings_bucket.prefix}amnezia_pc/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.pc
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.pc
