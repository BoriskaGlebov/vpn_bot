"""Общий справочник «нода → страна» для bot/ и api/ (#383)."""

import pytest

from shared.vpn.locations import NODE_COUNTRY_NAMES, resolve_country_name


@pytest.mark.parametrize("node_name", list(NODE_COUNTRY_NAMES))
def test_resolve_country_name_known_node(node_name):
    assert resolve_country_name(node_name, default="x") == NODE_COUNTRY_NAMES[node_name]


def test_resolve_country_name_unknown_node_returns_caller_default():
    assert resolve_country_name("unknown-node", default="x") == "x"


def test_resolve_country_name_none_returns_caller_default():
    assert resolve_country_name(None, default="x") == "x"
