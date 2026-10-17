from bot.core.config import settings_bot
from bot.users.enums import Location, PremiumLocation
from shared.enums.vpn_enum import VPNBackend

# Подписи кнопок для бэкенда — текст для пользователя, а не значения enum.
# Раньше это были значения отдельного bot/users/enums.py::VPNProtocol,
# дублировавшего имя с shared/enums/vpn_enum.py::VPNProtocol (протокол
# внутри бэкенда) при том, что по смыслу выбирал именно VPNBackend (см. #271).
BACKEND_LABELS: dict[VPNBackend, str] = {
    VPNBackend.AMNEZIA: "AmneziaVPN",
    VPNBackend.XRAY: "⚡ XRay Pro",
}


def vpn_button_text(backend: VPNBackend, location: Location | PremiumLocation) -> str:
    """Создает текст кнопок стилизованный под их локации."""
    node = settings_bot.vpn.nodes.get(location.value)
    flag = node.flag if node else "🏴‍☠️"
    return f"{flag} {BACKEND_LABELS[backend]} {location.name.title()}"
