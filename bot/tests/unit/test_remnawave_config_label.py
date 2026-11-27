from datetime import datetime

import pytest

from bot.users.schemas import SVPNConfigOut
from bot.users.utils.text_generator import format_config_location
from bot.utils.formatting import format_vpn_location
from bot.vpn.keyboards.inline_kb import my_configs_kb

pytestmark = pytest.mark.vpn


def _flatten(kb):
    """Возвращает плоский список кнопок из InlineKeyboardMarkup."""
    return [btn for row in kb.inline_keyboard for btn in row]


def _config(**kwargs) -> SVPNConfigOut:
    """Собирает SVPNConfigOut с обязательными полями по умолчанию."""
    defaults = {
        "id": 1,
        "file_name": "cfg",
        "pub_key": "key",
        "created_at": datetime(2026, 1, 1),
    }
    defaults.update(kwargs)
    return SVPNConfigOut(**defaults)


# ---------- format_config_location ----------


def test_format_config_location_remnawave_returns_backend_label():
    """backend=remnawave -> фирменная подпись бэкенда, а не локация по ноде."""
    assert format_config_location("remnawave", None) == "🚀 VPN Pro"


def test_format_config_location_remnawave_ignores_node_and_short():
    """backend=remnawave -> значок не зависит от node_name и флага short."""
    assert format_config_location("remnawave", "sof", short=True) == "🚀 VPN Pro"


def test_format_config_location_non_remnawave_delegates_to_format_vpn_location():
    """Прочие бэкенды -> метка как у format_vpn_location(node_name)."""
    assert format_config_location("xray", "sof") == format_vpn_location("sof")
    assert format_config_location(None, None) == format_vpn_location(None)


def test_format_config_location_passes_short_flag():
    """short прокидывается в format_vpn_location для не-remnawave."""
    assert format_config_location("xray", "sof", short=True) == format_vpn_location(
        "sof", short=True
    )


# ---------- my_configs_kb (кнопки удаления) ----------


def test_my_configs_kb_remnawave_button_shows_backend_label():
    """Кнопка remnawave-конфига -> «🚀 VPN Pro», без «❔»."""
    kb = my_configs_kb([_config(backend="remnawave", node_name=None)])
    text = _flatten(kb)[0].text
    assert "🚀 VPN Pro" in text
    assert "❔" not in text


def test_my_configs_kb_non_remnawave_button_shows_location():
    """Кнопка не-remnawave конфига -> локация по ноде, без «🚀 VPN Pro»."""
    kb = my_configs_kb([_config(backend="xray", node_name="sof")])
    text = _flatten(kb)[0].text
    assert "🚀 VPN Pro" not in text
    assert format_vpn_location("sof", short=True) in text
