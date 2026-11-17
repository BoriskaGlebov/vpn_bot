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
    assert set(standard) | set(premium) == {
        k for k, n in settings_bot.vpn.nodes.items() if n.enabled
    }
    assert all(not node.premium for node in standard.values())
    assert all(node.premium for node in premium.values())


def test_sof_node_is_premium_by_config():
    """В текущем конфиге `sof` — премиум-нода (перенесено из статичного enum).

    Проверяет флаг `premium` напрямую, а не через `premium_nodes()` —
    нода может быть временно отключена (`enabled=false`) через local.toml,
    но всё равно должна быть помечена как премиум.
    """
    sof = settings_bot.vpn.get("sof")
    assert sof.premium is True


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


def test_disabled_node_excluded_from_standard_nodes():
    """Нода с enabled=false не попадает в standard_nodes."""
    registry = VPNRegistry(
        nodes={
            "active": {"host": "h", "username": "u", "container": "c"},
            "inactive": {
                "host": "h",
                "username": "u",
                "container": "c",
                "enabled": False,
            },
        }
    )
    assert "active" in registry.standard_nodes()
    assert "inactive" not in registry.standard_nodes()


def test_disabled_node_excluded_from_premium_nodes():
    """Нода с enabled=false не попадает в premium_nodes."""
    registry = VPNRegistry(
        nodes={
            "std": {"host": "h", "username": "u", "container": "c"},
            "prem_on": {
                "host": "h",
                "username": "u",
                "container": "c",
                "premium": True,
                "enabled": True,
            },
            "prem_off": {
                "host": "h",
                "username": "u",
                "container": "c",
                "premium": True,
                "enabled": False,
            },
        }
    )
    assert "prem_on" in registry.premium_nodes()
    assert "prem_off" not in registry.premium_nodes()


def test_disabled_node_still_accessible_via_get():
    """Отключённая нода доступна через get() и get_optional()."""
    registry = VPNRegistry(
        nodes={
            "std": {"host": "h", "username": "u", "container": "c"},
            "off": {"host": "h", "username": "u", "container": "c", "enabled": False},
        }
    )
    assert registry.get("off").enabled is False
    assert registry.get_optional("off") is not None


def test_all_standard_nodes_disabled_raises():
    """Если все стандартные ноды disabled — ValidationError."""
    with pytest.raises(ValidationError):
        VPNRegistry(
            nodes={
                "a": {"host": "h", "username": "u", "container": "c", "enabled": False},
                "b": {"host": "h", "username": "u", "container": "c", "enabled": False},
            }
        )


def test_xray_available_property():
    """xray_available учитывает наличие секции и флаг enabled."""
    from bot.core.config import VPNNode

    node_no_xray = VPNNode(host="h", username="u", container="c")
    assert node_no_xray.xray_available is False

    node_xray_on = VPNNode(
        host="h",
        username="u",
        container="c",
        xray={
            "host": "x",
            "panel_prefix": "p",
            "subscription_prefix": "s",
            "panel_port": 1,
            "subscription_port": 2,
            "username": "a",
            "password": "b",
        },
    )
    assert node_xray_on.xray_available is True

    node_xray_off = VPNNode(
        host="h",
        username="u",
        container="c",
        xray={
            "host": "x",
            "panel_prefix": "p",
            "subscription_prefix": "s",
            "panel_port": 1,
            "subscription_port": 2,
            "username": "a",
            "password": "b",
            "enabled": False,
        },
    )
    assert node_xray_off.xray_available is False


def test_amnezia_available_property():
    """amnezia_available отражает флаг amnezia_enabled."""
    from bot.core.config import VPNNode

    node = VPNNode(host="h", username="u", container="c")
    assert node.amnezia_available is True

    node_off = VPNNode(host="h", username="u", container="c", amnezia_enabled=False)
    assert node_off.amnezia_available is False


def test_backward_compat_defaults_to_enabled():
    """Без указания флагов всё включено — backward compatibility."""
    from bot.core.config import VPNNode

    node = VPNNode(host="h", username="u", container="c")
    assert node.enabled is True
    assert node.amnezia_enabled is True
    assert node.amnezia_available is True
    assert node.xray_available is False  # xray не сконфигурирован
