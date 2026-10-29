"""Резолв страны VPN-ноды для отображения в админке (#383).

Название страны берётся из общего справочника `shared/vpn/locations.py` —
той же карты node_name → страна, которой пользуется `bot/utils/formatting.py`.
Флаг сюда не добавляется: он у `bot/` берётся динамически из
`settings_bot.vpn.nodes`, а `api/` к этой секции настроек бота доступа не
имеет (см. `api/core/config.py`) — подставлять здесь свой захардкоженный
флаг означало бы одну и ту же ноду показывать с разными флагами в боте и
в админке, если флаг в конфиге поменяют.
"""

from shared.vpn.locations import resolve_country_name

UNKNOWN_NODE_COUNTRY = "—"


def resolve_country(node_name: str | None) -> str:
    """Определяет страну ноды по её имени для отображения в админке.

    Args:
        node_name (str | None): Имя ноды (ключ `settings_bot.vpn.nodes`,
            например "de", "fr", "sof", "waw") либо None.

    Returns
        str: Человекочитаемое название страны, либо `UNKNOWN_NODE_COUNTRY`
            для неизвестной или отсутствующей ноды.

    """
    return resolve_country_name(node_name, default=UNKNOWN_NODE_COUNTRY)
