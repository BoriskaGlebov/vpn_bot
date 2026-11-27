from bot.core.config import settings_bot
from bot.utils.formatting import format_vpn_location
from shared.enums.vpn_enum import VPNBackend

# Подписи кнопок для бэкенда — текст для пользователя, а не значения enum.
# Раньше это были значения отдельного bot/users/enums.py::VPNProtocol,
# дублировавшего имя с shared/enums/vpn_enum.py::VPNProtocol (протокол
# внутри бэкенда) при том, что по смыслу выбирал именно VPNBackend.
BACKEND_LABELS: dict[VPNBackend, str] = {
    VPNBackend.AMNEZIA: "AmneziaVPN",
    VPNBackend.XRAY: "⚡ XRay Pro",
    VPNBackend.REMNAWAVE: "🚀 VPN Pro",
}


def format_config_location(
    backend: str | None, node_name: str | None, short: bool = False
) -> str:
    """Метка локации конфига для кнопок удаления и списка подписки.

    У Remnawave локации нет (одна панель, `node_name=None`) — показываем
    фирменную подпись бэкенда (`BACKEND_LABELS`) вместо «❔ неизвестно»,
    которое отдаёт `format_vpn_location` для пустой ноды. Для прочих
    бэкендов — страна по ноде, как раньше.

    Args:
        backend: Бэкенд конфига ("amnezia"/"xray"/"remnawave" или `None`
            у старых записей).
        node_name: Имя ноды/локации конфига.
        short: Компактный вид для кнопок (прокидывается в
            `format_vpn_location`); для Remnawave не влияет.

    Returns
        str: Метка локации конфига.

    """
    if backend == VPNBackend.REMNAWAVE:
        return BACKEND_LABELS[VPNBackend.REMNAWAVE]
    return format_vpn_location(node_name, short=short)


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
