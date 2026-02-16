from bot.config import settings_bot, settings_bucket
from bot.help.utils.common_device import Device


class TVDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Smart TV."""

    PREFIX = f"{settings_bucket.prefix}amnezia_wg/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.tv
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.tv
