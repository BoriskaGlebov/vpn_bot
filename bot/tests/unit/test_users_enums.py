import pytest
from pydantic import ValidationError

from bot.core.config import VPNRegistry, settings_bot


def test_standard_and_premium_nodes_partition_configured_nodes():
    """`standard_nodes`/`premium_nodes` — разбиение `nodes` без пересечений и пропусков.

    Регрессия на пожелание после #268: раньше набор локаций был статическим
    enum (`Location`/`PremiumLocation`) с ключами нод, прописанными в коде
    руками — новая нода в конфиге требовала правки кода. Теперь деление на
    стандартные/премиум идёт по `VPNNode.premium` из конфига.
    """
    standard = settings_bot.vpn.standard_nodes()
    premium = settings_bot.vpn.premium_nodes()

    assert set(standard) & set(premium) == set()
    assert set(standard) | set(premium) == set(settings_bot.vpn.nodes)
    assert all(not node.premium for node in standard.values())
    assert all(node.premium for node in premium.values())


def test_sof_node_is_premium_by_config():
    """В текущем конфиге `sof` — премиум-нода (перенесено из статичного enum)."""
    assert "sof" in settings_bot.vpn.premium_nodes()
    assert "sof" not in settings_bot.vpn.standard_nodes()


def test_registry_rejects_all_premium_nodes():
    """Хотя бы одна стандартная нода обязана быть сконфигурирована.

    Раньше эту гарантию давало наличие ноды с конкретным ключом "main"
    (`Location.MAIN`, статический enum); теперь — любая нода с
    `premium=False`, независимо от ключа. Если все ноды премиум — конфиг
    не должен собраться вовсе, а не молча оставить стандартных
    пользователей без локаций.
    """
    with pytest.raises(ValidationError):
        VPNRegistry(
            nodes={
                "only_premium": {
                    "host": "h",
                    "username": "u",
                    "container": "c",
                    "premium": True,
                }
            }
        )


def test_registry_accepts_single_standard_node():
    registry = VPNRegistry(
        nodes={"anything": {"host": "h", "username": "u", "container": "c"}}
    )
    assert "anything" in registry.standard_nodes()
