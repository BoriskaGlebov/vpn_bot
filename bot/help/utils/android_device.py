from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class AndroidDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Android."""

    PREFIX = f"{settings_bucket.prefix}amnezia_android/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.android
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.android
