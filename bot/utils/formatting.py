from datetime import datetime

from aiogram.types import User

from bot.core.config import settings_bot


def format_username(user: User | None) -> str:
    """Возвращает читаемое отображаемое имя пользователя Telegram.

    Args:
        user (User | None): Пользователь Telegram или None.

    Returns
        str: "@username", либо полное имя/"Гость_{id}" если username не задан,
        либо "Гость" если пользователь неизвестен.

    """
    if user is None:
        return "Гость"
    if user.username:
        return f"@{user.username}"
    return user.full_name or f"Гость_{user.id}"


def format_subscription_end_date(end_date: datetime | None) -> str:
    """Форматирует дату окончания подписки для показа пользователю.

    Args:
        end_date (datetime | None): Дата окончания подписки.

    Returns
        str: Дата в формате YYYY-MM-DD, либо "бессрочно", если не задана.

    """
    return end_date.strftime("%Y-%m-%d") if end_date else "бессрочно"


def format_vpn_config_date(created_at: datetime) -> str:
    """Форматирует дату создания VPN-конфига для показа пользователю.

    Args:
        created_at (datetime): Дата и время создания конфига.

    Returns
        str: Дата в формате YYYY-MM-DD.

    """
    return created_at.strftime("%Y-%m-%d")


NODE_COUNTRY_NAMES: dict[str, str] = {
    "de": "Германия (Франкфурт)",
    "fr": "Франция (Париж)",
    "fi": "Финляндия",
    "sof": "Болгария (София)",
    "waw": "Польша (Варшава)",
}


def format_vpn_location(node_name: str | None, short: bool = False) -> str:
    """Возвращает человекочитаемую локацию конфига по имени ноды.

    Args:
        node_name (str | None): Имя ноды/локации (ключ в settings_bot.vpn.nodes).
        short (bool): Если True — компактный вид "{flag} {location_prefix}"
            для кнопок, где место ограничено лимитом Telegram. Если False —
            полный вид "{flag} {страна} ({location_prefix})" для текста
            сообщений.

    Returns
        str: Отображение локации для сконфигурированной ноды, иначе
        "❔ неизвестно" (нода могла быть выведена из эксплуатации или не
        определена у старых записей).

    """
    node = settings_bot.vpn.get_optional(node_name) if node_name else None
    if node is None:
        return "❔ неизвестно"
    if short:
        return f"{node.flag} {node.location_prefix}"
    country = NODE_COUNTRY_NAMES.get(node_name or "", node.location_prefix)
    return f"{node.flag} {country} ({node.location_prefix})"
