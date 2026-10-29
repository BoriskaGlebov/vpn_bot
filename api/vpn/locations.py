"""Справочник «нода → страна» для отображения VPN-конфига в админке."""

NODE_COUNTRIES: dict[str, str] = {
    "de": "Германия 🇩🇪",
    "fr": "Франция 🇫🇷",
    "sof": "Болгария 🇧🇬",
    "waw": "Польша 🇵🇱",
    "fi": "Финляндия 🇫🇮",
}

UNKNOWN_NODE_COUNTRY = "—"


def resolve_country(node_name: str | None) -> str:
    """Определяет страну ноды по её имени для отображения в админке.

    `api/` не имеет доступа к секции `vpn.nodes` настроек бота — она
    объявлена только в `bot/core/config.py` (`Settings.vpn`), а
    `SettingsAPI` её не включает (разные физические окружения с разными
    нодами описаны в `app_config*.toml`). Поэтому карта нода → страна
    задаётся явной константой здесь и обновляется вручную при добавлении
    новой ноды в конфиг бота.

    Args:
        node_name (str | None): Имя ноды (ключ `settings_bot.vpn.nodes`,
            например "de", "fr", "sof", "waw") либо None.

    Returns
        str: Человекочитаемое название страны с флагом, либо
            `UNKNOWN_NODE_COUNTRY` для неизвестной или отсутствующей ноды.

    """
    if node_name is None:
        return UNKNOWN_NODE_COUNTRY
    return NODE_COUNTRIES.get(node_name, UNKNOWN_NODE_COUNTRY)
