from bot.core.config import settings_bot
from bot.help.utils.common_device import Device


class TVDevice(Device):
    """Класс устройства, отвечающий за отправку инструкций для Smart TV."""

    PREFIX = f"{settings_bot.bucket.prefix}amnezia_wg/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.tv
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.tv
