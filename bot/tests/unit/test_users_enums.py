from bot.core.config import settings_bot
from bot.users.enums import (
    Location,
    PremiumLocation,
    available_locations,
    available_premium_locations,
)


def test_location_values_are_node_keys():
    """Значение `Location`/`PremiumLocation` — ключ ноды, а не `location_prefix`.

    Регрессия на #268: раньше значением был `location_prefix` ноды (напр.
    "fr" на prod при ключе ноды "main"), и
    `settings_bot.vpn.nodes.get(location.value)` не находил ноду вообще
    никогда — рабочим был только обходной путь через `location.name.lower()`.
    """
    assert Location.MAIN.value == "main"
    assert Location.FINLAND.value == "fi"
    assert Location.WAW.value == "waw"
    assert PremiumLocation.SOFIA.value == "sof"


def test_available_locations_resolve_directly_by_value():
    """Для каждой сконфигурированной локации нода находится по `loc.value`.

    Без обходных путей (`.name.lower()`, поиск подстрокой в тексте кнопки).
    """
    for loc in available_locations():
        assert settings_bot.vpn.nodes.get(loc.value) is not None

    for loc in available_premium_locations():
        assert settings_bot.vpn.nodes.get(loc.value) is not None


def test_available_locations_is_subset_of_all_configured_nodes():
    """`available_locations`/`available_premium_locations` не выдумывают локации.

    Оба набора — подмножество реально сконфигурированных нод, определяемое
    статически объявленными `Location`/`PremiumLocation`, а не наоборот.
    """
    configured = set(settings_bot.vpn.nodes)

    assert {loc.value for loc in available_locations()} <= configured
    assert {loc.value for loc in available_premium_locations()} <= configured
