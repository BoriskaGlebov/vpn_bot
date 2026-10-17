from bot.core.config import settings_bot
from bot.users.enums import Location, PremiumLocation


def vpn_button_text(protocol: str, location: Location | PremiumLocation) -> str:
    """Создает текст кнопок стилизованный под их локации."""
    node = settings_bot.vpn.nodes.get(location.value)
    flag = node.flag if node else "🏴‍☠️"
    return f"{flag} {protocol} {location.name.title()}"
