"""Резолв страны VPN-ноды для отображения в админке (#383).

Название страны берётся из общего справочника `shared/vpn/locations.py` —
той же карты node_name → страна, которой пользуется `bot/utils/formatting.py`.

Флаг здесь — статическое зеркало `settings_bot.vpn.nodes[node].flag`:
`api/` к этой секции настроек бота доступа не имеет (см. `api/core/config.py`),
поэтому значение продублировано руками. Если флаг ноды поменяют в
`app_config*.toml`, его придётся обновить и здесь — иначе разойдётся с тем,
что видит пользователь в боте.
"""

from shared.vpn.locations import resolve_country_name

UNKNOWN_NODE_COUNTRY = "—"

NODE_FLAGS: dict[str, str] = {
    "de": "🇩🇪",
    "fr": "🇫🇷",
    "sof": "🇧🇬",
    "waw": "🇵🇱",
    "fi": "🇫🇮",
}


def resolve_country(node_name: str | None) -> str:
    """Определяет страну ноды (с флагом) по её имени для отображения в админке.

    Args:
        node_name (str | None): Имя ноды (ключ `settings_bot.vpn.nodes`,
            например "de", "fr", "sof", "waw") либо None.

    Returns
        str: "{флаг} {страна}", либо просто `UNKNOWN_NODE_COUNTRY` для
            неизвестной или отсутствующей ноды (без флага — его тоже
            нет).

    """
    name = resolve_country_name(node_name, default=UNKNOWN_NODE_COUNTRY)
    flag = NODE_FLAGS.get(node_name) if node_name else None
    return f"{flag} {name}" if flag else name
