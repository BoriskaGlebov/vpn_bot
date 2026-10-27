"""Отзыв доступа всех VPN-конфигов пользователя при удалении из админки (#290/#246)."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from api.app_error.base_error import (
    BotChannelUnavailableError,
    UserVPNRevokeIncompleteError,
    VPNRevokeFailedError,
)
from api.users.admin import UserAdmin
from api.users.models import User
from api.vpn.models import VPNConfig, VPNConfigStatus
from shared.enums.vpn_enum import VPNRevokeStatus


def make_config(file_name: str = "cfg.conf", **overrides: object) -> VPNConfig:
    defaults: dict = dict(
        id=1,
        user_id=10,
        file_name=file_name,
        pub_key="pub",
        status=VPNConfigStatus.ACTIVE,
        node_name="fr",
        backend="amnezia",
        protocol="wg_v2",
        config_ids=None,
        created_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return VPNConfig(**defaults)


def make_user(vpn_configs: list[VPNConfig]) -> User:
    user = User(id=10, telegram_id=999, username="test", has_used_trial=False)
    user.vpn_configs = vpn_configs
    return user


@pytest.fixture
def admin() -> UserAdmin:
    return UserAdmin()


@pytest.mark.asyncio
async def test_on_model_delete_no_configs_skips_bot_call(admin, monkeypatch):
    """У пользователя нет VPN-конфигов — бот не вызывается вовсе."""
    client = AsyncMock()
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    user = make_user([])
    await admin.on_model_delete(user, request=None)

    client.revoke_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_model_delete_revokes_all_configs(admin, monkeypatch):
    """Все конфиги подтвердили отзыв — исключения нет, пользователя можно удалять."""
    client = AsyncMock()
    client.revoke_config.return_value = VPNRevokeStatus.OK
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    configs = [make_config("a.conf"), make_config("b.conf", id=2)]
    user = make_user(configs)

    await admin.on_model_delete(user, request=None)

    assert client.revoke_config.await_count == 2


@pytest.mark.asyncio
async def test_on_model_delete_partial_failure_aborts_and_lists_remaining(
    admin, monkeypatch
):
    """Один конфиг не отозван — удаление прерывается, второй конфиг тоже
    пробуется (не останавливаемся на первой ошибке), ошибка перечисляет
    только реально неотозванные конфиги.
    """
    client = AsyncMock()
    client.revoke_config.side_effect = [
        VPNRevokeStatus.OK,
        VPNRevokeFailedError("b.conf", "нода недоступна"),
    ]
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    configs = [make_config("a.conf"), make_config("b.conf", id=2)]
    user = make_user(configs)

    with pytest.raises(UserVPNRevokeIncompleteError) as exc_info:
        await admin.on_model_delete(user, request=None)

    assert exc_info.value.details["failed_configs"] == ["b.conf"]
    assert client.revoke_config.await_count == 2


@pytest.mark.asyncio
async def test_on_model_delete_bot_unavailable_lists_all_configs(admin, monkeypatch):
    """Бот недоступен для любого конфига — в ошибке перечислены все конфиги."""
    client = AsyncMock()
    client.revoke_config.side_effect = BotChannelUnavailableError("бот недоступен")
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    configs = [make_config("a.conf"), make_config("b.conf", id=2)]
    user = make_user(configs)

    with pytest.raises(UserVPNRevokeIncompleteError) as exc_info:
        await admin.on_model_delete(user, request=None)

    assert exc_info.value.details["failed_configs"] == ["a.conf", "b.conf"]
