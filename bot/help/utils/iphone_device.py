from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class IphoneDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для iPhone."""

    PREFIX = f"{settings_bucket.prefix}amnezia_iphone/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.iphone
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.iphone
