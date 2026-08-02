from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.app_error.api_error import APIClientError
from bot.app_error.schema import ErrorDetail
from bot.vpn.DTO import UserUUID
from bot.vpn.utils.x_ray_config import ThreeXUIAdapter


@pytest.fixture
def api_client():
    client = AsyncMock()
    return client


@pytest.fixture
def adapter(api_client):
    return ThreeXUIAdapter(
        api_client=api_client,
        prefix="/panel",
        correct_inbounds=[],
        username="admin",
        password="admin",
        host="example.com",
        sub_port=443,
        sub_prefix="sub",
        location_prefix="loc_",
    )


@pytest.mark.asyncio
async def test_login(adapter):
    adapter.api.post = AsyncMock(return_value=({"success": True, "ok": True}, 200))

    res, status = await adapter._login(
        user_credentials=MagicMock(model_dump=lambda: {"u": "a"})
    )

    assert status == 200
    assert res == {"success": True, "ok": True}
    adapter.api.post.assert_called_once()


@pytest.mark.asyncio
async def test_login_auth_error(adapter):
    from bot.vpn.utils.x_ray_exceptions import ThreeXUIAuthError

    adapter.api.post = AsyncMock(
        return_value=({"success": False, "msg": "Wrong credentials"}, 200)
    )

    with pytest.raises(ThreeXUIAuthError):
        await adapter._login(user_credentials=MagicMock(model_dump=lambda: {"u": "a"}))


@pytest.mark.asyncio
async def test_logout_success(adapter):
    adapter.api.get = AsyncMock()

    await adapter._logout()

    adapter.api.get.assert_called_once()


@pytest.mark.asyncio
async def test_logout_error_ignored(adapter):
    adapter.api.get = AsyncMock(
        side_effect=APIClientError(ErrorDetail(code="fail", message="fail"))
    )

    await adapter._logout()


@pytest.mark.asyncio
async def test_get_all_inbounds(adapter):
    adapter.api.get = AsyncMock(
        return_value={
            "success": True,
            "obj": [{"id": 1, "remark": "test", "enable": True, "port": 1000}],
        }
    )

    result = await adapter._get_all_inbounds()

    assert len(result) == 1
    assert result[0].id == 1


@pytest.mark.asyncio
async def test_get_all_users(adapter):
    adapter.api.get = AsyncMock(
        return_value={
            "success": True,
            "obj": [
                {
                    "clientStats": [
                        {"uuid": "123"},
                        {"uuid": "456"},
                    ]
                }
            ],
        }
    )

    result = await adapter._get_all_users()

    assert len(result) == 2
    assert {u.conf_uuid for u in result} == {"123", "456"}


@dataclass
class FakeInboundCfg:
    port: int
    name: str


@pytest.mark.asyncio
async def test_get_inbound_success(adapter):
    adapter._get_all_inbounds = AsyncMock(
        return_value=[
            MagicMock(port=1000, remark="A", id=1),
            MagicMock(port=2000, remark="B", id=2),
        ]
    )

    adapter.inbounds_name = [
        FakeInboundCfg(port=1000, name="A"),
    ]

    result = await adapter._get_inbound(adapter.inbounds_name)

    assert len(result) == 1
    assert result[0].id == 1


@pytest.mark.asyncio
async def test_add_new_config(adapter):
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()
    adapter._restart_x_ray = AsyncMock()
    adapter._add_user = AsyncMock()

    adapter._get_inbound = AsyncMock(return_value=[MagicMock(id=1, remark="test")])

    with (
        patch("bot.vpn.utils.x_ray_config.uuid.uuid4", return_value="uuid-1"),
        patch("bot.vpn.utils.x_ray_config.time.time", return_value=1000),
    ):
        result, url = await adapter.add_new_config(
            tg_id=123,
            days=1,
        )

    assert "config_ids" in result
    assert "sub_ids" in result
    assert "uuid-1" in result["config_ids"]
    assert "user_123" in url

    adapter._add_user.assert_called_once()
    adapter._logout.assert_called_once()


@pytest.mark.asyncio
async def test_extend_config_invalid_days(adapter):
    from bot.vpn.utils.x_ray_exceptions import ThreeXUIInvalidExpiryError

    with pytest.raises(ThreeXUIInvalidExpiryError):
        await adapter.extend_config(config_ids=["a"], days=0)


@pytest.mark.asyncio
async def test_extend_config_success(adapter):
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()
    adapter._restart_x_ray = AsyncMock()
    adapter._update_client = AsyncMock()

    adapter._get_inbound = AsyncMock(return_value=[MagicMock(id=1), MagicMock(id=2)])
    adapter._get_inbound_clients = AsyncMock(
        side_effect=[
            [{"id": "abc", "email": "user_1"}],
            [{"id": "def", "email": "user_2"}],
        ]
    )

    with patch("bot.vpn.utils.x_ray_config.time.time", return_value=1000):
        result = await adapter.extend_config(config_ids=["abc", "def"], days=5)

    assert set(result) == {"abc", "def"}
    assert adapter._update_client.await_count == 2
    adapter._restart_x_ray.assert_awaited_once()
    adapter._logout.assert_awaited_once()


@pytest.mark.asyncio
async def test_extend_config_not_found_raises(adapter):
    from bot.vpn.utils.x_ray_exceptions import ThreeXUIConfigNotFoundError

    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()
    adapter._restart_x_ray = AsyncMock()

    adapter._get_inbound = AsyncMock(return_value=[MagicMock(id=1)])
    adapter._get_inbound_clients = AsyncMock(return_value=[{"id": "other"}])

    with pytest.raises(ThreeXUIConfigNotFoundError):
        await adapter.extend_config(config_ids=["missing"], days=5)


@pytest.mark.asyncio
async def test_delete_config_not_found(adapter):
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()
    adapter._get_all_users = AsyncMock(return_value=[])

    result = await adapter.delete_config("missing-id")

    assert result is False
    adapter._logout.assert_not_called()


@pytest.mark.asyncio
async def test_delete_config_success(adapter):
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()

    adapter._get_all_users = AsyncMock(return_value=[UserUUID(conf_uuid="abc")])

    adapter._get_inbound = AsyncMock(return_value=[MagicMock(id=1), MagicMock(id=2)])

    adapter.api.post = AsyncMock()

    result = await adapter.delete_config("abc")

    assert result is True
    assert adapter.api.post.call_count == 2
    adapter._logout.assert_called_once()
