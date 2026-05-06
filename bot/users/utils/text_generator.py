from bot.core.config import settings_bot
from bot.users.enums import Location


def vpn_button_text(protocol: str, location: Location) -> str:
    """Создает текст кнопок стилизованный под их локации."""
    loc = settings_bot.vpn.nodes.get(location.value)
    if loc:
        return f"{loc.flag} {protocol} {location.name.title()}"
    elif flag := settings_bot.vpn.nodes.get(location.name.lower()):
        return f"{flag.flag} {protocol} {location.name.title()}"
    else:
        return f"🏴‍☠️ {protocol} {location.name.title()}"
