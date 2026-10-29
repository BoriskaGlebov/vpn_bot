"""Резолв страны VPN-ноды по имени (#383)."""

import pytest

from api.vpn.locations import UNKNOWN_NODE_COUNTRY, resolve_country
from shared.vpn.locations import NODE_COUNTRY_NAMES


@pytest.mark.parametrize("node_name", list(NODE_COUNTRY_NAMES))
def test_resolve_country_known_node(node_name):
    assert resolve_country(node_name) == NODE_COUNTRY_NAMES[node_name]


def test_resolve_country_unknown_node_returns_safe_default():
    assert resolve_country("unknown-node") == UNKNOWN_NODE_COUNTRY


def test_resolve_country_none_returns_safe_default():
    assert resolve_country(None) == UNKNOWN_NODE_COUNTRY
