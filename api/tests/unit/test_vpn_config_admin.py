"""Отзыв доступа VPN-конфига на ноде при удалении из админки (#290/#382)."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from api.app_error.base_error import BotChannelUnavailableError, VPNRevokeFailedError
from api.users.models import User
from api.vpn.admin import VPNConfigAdmin
from api.vpn.models import VPNConfig, VPNConfigStatus
from shared.enums.vpn_enum import VPNRevokeStatus


def make_config(**overrides: object) -> VPNConfig:
    defaults: dict = dict(
        id=1,
        user_id=10,
        file_name="cfg.conf",
        pub_key="pub",
        status=VPNConfigStatus.ACTIVE,
        node_name="fr",
        backend="amnezia",
        protocol="wg_v2",
        config_ids=None,
        created_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    config = VPNConfig(**defaults)
    config.user = User(id=10, telegram_id=999, username="test", has_used_trial=False)
    return config


@pytest.fixture
def admin() -> VPNConfigAdmin:
    return VPNConfigAdmin()


@pytest.mark.asyncio
async def test_on_model_delete_revokes_config_on_node(admin, monkeypatch):
    """OK/NOT_FOUND — исключение не поднимается, SQLAdmin удалит запись."""
    client = AsyncMock()
    client.revoke_config.return_value = VPNRevokeStatus.OK
    monkeypatch.setattr("api.vpn.admin.get_bot_channel_client", lambda: client)

    config = make_config()
    await admin.on_model_delete(config, request=None)

    client.revoke_config.assert_awaited_once()
    tg_id, config_out = client.revoke_config.await_args.args
    assert tg_id == 999
    assert config_out.file_name == "cfg.conf"
    assert config_out.node_name == "fr"


@pytest.mark.parametrize(
    "error",
    [
        BotChannelUnavailableError("бот недоступен"),
        VPNRevokeFailedError("cfg.conf", "нода недоступна"),
    ],
)
@pytest.mark.asyncio
async def test_on_model_delete_propagates_unconfirmed_revoke(admin, monkeypatch, error):
    """Неподтверждённый отзыв не глотается — запись не должна удаляться."""
    client = AsyncMock()
    client.revoke_config.side_effect = error
    monkeypatch.setattr("api.vpn.admin.get_bot_channel_client", lambda: client)

    config = make_config()
    with pytest.raises(type(error)):
        await admin.on_model_delete(config, request=None)
