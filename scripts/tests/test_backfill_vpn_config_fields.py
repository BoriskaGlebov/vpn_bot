from types import SimpleNamespace
from typing import cast

from api.vpn.models import VPNConfig
from scripts.backfill_vpn_config_fields import build_prefix_to_node, infer_fields


def _config(file_name: str, pub_key: str) -> VPNConfig:
    return cast(VPNConfig, SimpleNamespace(id=1, file_name=file_name, pub_key=pub_key))


def test_build_prefix_to_node_from_real_settings() -> None:
    prefix_to_node = build_prefix_to_node()

    assert prefix_to_node["DE"] == "main"
    assert prefix_to_node["SOF"] == "sof"


def test_infer_fields_amnezia() -> None:
    prefix_to_node = {"DE": "main"}
    config = _config(
        file_name="WGDEc52645.conf / VPNDEc52645.vpn / QRDEc52645.png",
        pub_key="AbCdEf123pubkey=",
    )

    fields = infer_fields(config, prefix_to_node)

    assert fields == {
        "node_name": "main",
        "backend": "amnezia",
        "protocol": "wg_v3",
        "config_ids": None,
    }


def test_infer_fields_xray() -> None:
    prefix_to_node = {"SOF": "sof"}
    config = _config(
        file_name="SOFuser_8140810615_8e0f9ced",
        pub_key='["cfg1", "cfg2"]',
    )

    fields = infer_fields(config, prefix_to_node)

    assert fields == {
        "node_name": "sof",
        "backend": "xray",
        "protocol": None,
        "config_ids": ["cfg1", "cfg2"],
    }


def test_infer_fields_xray_legacy_subid_without_suffix() -> None:
    """Старый детерминированный subId (до фикса шага 2) — без случайного суффикса."""
    prefix_to_node = {"SOF": "sof"}
    config = _config(file_name="SOFuser_123456789", pub_key='["cfg1"]')

    fields = infer_fields(config, prefix_to_node)

    assert fields is not None
    assert fields["node_name"] == "sof"
    assert fields["backend"] == "xray"


def test_infer_fields_unknown_prefix_returns_none() -> None:
    prefix_to_node = {"DE": "main"}
    config = _config(
        file_name="WGXXc52645.conf / VPNXXc52645.vpn / QRXXc52645.png",
        pub_key="pubkey",
    )

    assert infer_fields(config, prefix_to_node) is None


def test_infer_fields_unparseable_filename_returns_none() -> None:
    prefix_to_node = {"DE": "main"}
    config = _config(file_name="totally-unexpected-name", pub_key="pubkey")

    assert infer_fields(config, prefix_to_node) is None
