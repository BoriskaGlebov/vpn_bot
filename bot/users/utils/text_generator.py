from bot.core.config import settings_bot
from shared.enums.vpn_enum import VPNBackend

# Подписи кнопок для бэкенда — текст для пользователя, а не значения enum.
# Раньше это были значения отдельного bot/users/enums.py::VPNProtocol,
# дублировавшего имя с shared/enums/vpn_enum.py::VPNProtocol (протокол
# внутри бэкенда) при том, что по смыслу выбирал именно VPNBackend.
BACKEND_LABELS: dict[VPNBackend, str] = {
    VPNBackend.AMNEZIA: "AmneziaVPN",
    VPNBackend.XRAY: "⚡ XRay Pro",
}


def vpn_button_text(backend: VPNBackend, location: str) -> str:
    """Создаёт текст кнопки для локации.

    Args:
        backend: Бэкенд, под который формируется кнопка.
        location: Ключ ноды в `settings_bot.vpn.nodes`.

    Отображаемое название локации — `location_prefix` ноды (например "FR"
    для Франции), а не её ключ ("main") — ключ ноды не несёт смысла для
    пользователя, различить локации он может только по флагу и подписи.

    """
    node = settings_bot.vpn.nodes.get(location)
    flag = node.flag if node else "🏴‍☠️"
    display = node.location_prefix if node else location.upper()
    return f"{flag} {BACKEND_LABELS[backend]} {display}"
