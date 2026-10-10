from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.app_error.api_error import APIClientError
from bot.app_error.schema import ErrorDetail
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
async def test_add_new_config_warns_when_restart_failed(adapter):
    """Неудачный _restart_x_ray (None) не должен ломать создание конфигурации."""
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()
    adapter._restart_x_ray = AsyncMock(return_value=None)
    adapter._add_user = AsyncMock()
    adapter._get_inbound = AsyncMock(return_value=[MagicMock(id=1, remark="test")])

    with (
        patch("bot.vpn.utils.x_ray_config.uuid.uuid4", return_value="uuid-1"),
        patch("bot.vpn.utils.x_ray_config.time.time", return_value=1000),
        patch("bot.vpn.utils.x_ray_config.logger") as mock_logger,
    ):
        result, url = await adapter.add_new_config(tg_id=123, days=1)

    assert "uuid-1" in result["config_ids"]
    mock_logger.warning.assert_called_once()


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
async def test_extend_config_warns_when_restart_failed(adapter):
    """Неудачный _restart_x_ray (None) не должен ломать продление конфигураций."""
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()
    adapter._restart_x_ray = AsyncMock(return_value=None)
    adapter._update_client = AsyncMock()
    adapter._get_inbound = AsyncMock(return_value=[MagicMock(id=1)])
    adapter._get_inbound_clients = AsyncMock(return_value=[{"id": "abc"}])

    with (
        patch("bot.vpn.utils.x_ray_config.time.time", return_value=1000),
        patch("bot.vpn.utils.x_ray_config.logger") as mock_logger,
    ):
        result = await adapter.extend_config(config_ids=["abc"], days=5)

    assert result == ["abc"]
    mock_logger.warning.assert_called_once()


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
    adapter._get_inbounds_with_clients = AsyncMock(return_value=[])
    adapter.inbounds_name = []

    result = await adapter.delete_config("missing-id")

    assert result is False
    # _session() гарантирует logout даже при раннем return (config не найден).
    adapter._logout.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_config_success(adapter):
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()

    inb1 = MagicMock(port=1000, remark="A", id=1)
    inb2 = MagicMock(port=2000, remark="B", id=2)
    adapter._get_inbounds_with_clients = AsyncMock(
        return_value=[(inb1, {"abc"}), (inb2, {"abc"})]
    )
    adapter.inbounds_name = [
        FakeInboundCfg(port=1000, name="A"),
        FakeInboundCfg(port=2000, name="B"),
    ]
    adapter.api.post = AsyncMock(return_value=({"success": True}, 200))

    result = await adapter.delete_config("abc")

    assert result is True
    assert adapter.api.post.call_count == 2
    adapter._logout.assert_called_once()


@pytest.mark.asyncio
async def test_delete_config_found_but_not_in_configured_inbounds(adapter):
    """Клиент есть на панели, но не в ожидаемых inbound этой ноды — считаем отсутствующим."""
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()

    inb1 = MagicMock(port=1000, remark="A", id=1)
    adapter._get_inbounds_with_clients = AsyncMock(return_value=[(inb1, set())])
    adapter.inbounds_name = [FakeInboundCfg(port=1000, name="A")]
    adapter.api.post = AsyncMock()

    result = await adapter.delete_config("abc")

    assert result is False
    adapter.api.post.assert_not_called()


@pytest.mark.asyncio
async def test_delete_config_panel_failure_raises(adapter):
    """success:false на inbound, где клиент реально найден — ошибка, не тихий True."""
    from bot.vpn.utils.x_ray_exceptions import ThreeXUIRequestError

    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()

    inb1 = MagicMock(port=1000, remark="A", id=1)
    adapter._get_inbounds_with_clients = AsyncMock(return_value=[(inb1, {"abc"})])
    adapter.inbounds_name = [FakeInboundCfg(port=1000, name="A")]
    adapter.api.post = AsyncMock(
        return_value=({"success": False, "msg": "client busy"}, 200)
    )

    with pytest.raises(ThreeXUIRequestError):
        await adapter.delete_config("abc")

    adapter._logout.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_config_partial_success_across_inbounds(adapter):
    """Успех хоть на одном inbound, где клиент реально есть — считается успехом."""
    adapter._login = AsyncMock()
    adapter._logout = AsyncMock()

    inb1 = MagicMock(port=1000, remark="A", id=1)
    inb2 = MagicMock(port=2000, remark="B", id=2)
    adapter._get_inbounds_with_clients = AsyncMock(
        return_value=[(inb1, {"abc"}), (inb2, {"abc"})]
    )
    adapter.inbounds_name = [
        FakeInboundCfg(port=1000, name="A"),
        FakeInboundCfg(port=2000, name="B"),
    ]
    adapter.api.post = AsyncMock(
        side_effect=[
            ({"success": False, "msg": "busy"}, 200),
            ({"success": True}, 200),
        ]
    )

    result = await adapter.delete_config("abc")

    assert result is True


@pytest.mark.asyncio
async def test_get_inbounds_with_clients(adapter):
    adapter.api.get = AsyncMock(
        return_value={
            "success": True,
            "obj": [
                {
                    "id": 1,
                    "remark": "A",
                    "enable": True,
                    "port": 1000,
                    "clientStats": [{"uuid": "abc"}],
                },
                {
                    "id": 2,
                    "remark": "B",
                    "enable": True,
                    "port": 2000,
                    "clientStats": [],
                },
            ],
        }
    )

    result = await adapter._get_inbounds_with_clients()

    assert len(result) == 2
    inb0, uuids0 = result[0]
    assert inb0.id == 1
    assert uuids0 == {"abc"}
    inb1, uuids1 = result[1]
    assert inb1.id == 2
    assert uuids1 == set()
