from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from bot.app_error.api_error import APIClientError
from bot.integrations.api_client import APIClient
from bot.scheduler.adapter import SchedulerAPIAdapter
from bot.scheduler.enums import SubscriptionEventType
from bot.scheduler.schemas import (
    AdminNotifyEventSchema,
    CheckAllSubscriptionsResponse,
    DeletedVPNConfigSchema,
    DeleteProxyEventSchema,
    DeleteVPNConfigsEventSchema,
    SubscriptionStatsSchema,
    UserNotifyEventSchema,
)
from bot.scheduler.services import SchedulerBotService


@pytest.fixture
def service():
    adapter = AsyncMock()
    vpn_adapter = AsyncMock()
    xray_adapter = AsyncMock()
    bot = AsyncMock(spec=Bot)

    return SchedulerBotService(
        adapter=adapter,
        bot=bot,
        vpn_adapter=vpn_adapter,
        xray_adapter=xray_adapter,
    )


@pytest.fixture
async def api_client():
    clients = []

    async def _create(handler):
        transport = httpx.MockTransport(handler)
        client = APIClient(base_url="test", port=8000)
        client._client = httpx.AsyncClient(
            transport=transport,
            base_url=client.base_url,
        )
        clients.append(client)
        return client

    yield _create

    for client in clients:
        await client._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_data, expected_class",
    [
        (
            {
                "type": "user_notify",
                "user_id": 1,
                "message": "User message",
                "subscription_type": "premium",
                "remaining_days": 10,
                "active_sbs": True,
            },
            UserNotifyEventSchema,
        ),
        (
            {
                "type": "delete_vpn_configs",
                "user_id": 2,
                "configs": [
                    {"file_name": "vpn1.ovpn", "pub_key": "key1"},
                    {"file_name": "vpn2.ovpn", "pub_key": "key2"},
                ],
            },
            DeleteVPNConfigsEventSchema,
        ),
        (
            {"type": "delete_proxy", "user_id": 3},
            DeleteProxyEventSchema,
        ),
        (
            {"type": "admin_notify", "user_id": 4, "message": "Admin alert"},
            AdminNotifyEventSchema,
        ),
    ],
)
async def test_check_all_events(api_client, event_data, expected_class):
    """Тестирует SchedulerAPIAdapter.check_all с разными событиями."""

    async def handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            json={
                "stats": {"checked": 100, "expired": 5, "configs_deleted": 2},
                "events": [event_data],
            },
        )

    client = await api_client(handler)
    adapter = SchedulerAPIAdapter(client)

    response: CheckAllSubscriptionsResponse = await adapter.check_all()

    # Проверка статистики
    assert response.stats.checked == 100
    assert response.stats.expired == 5
    assert response.stats.configs_deleted == 2

    # Проверка события
    assert len(response.events) == 1
    event = response.events[0]
    assert isinstance(event, expected_class)
    assert event.user_id == event_data["user_id"]
    if hasattr(event, "message"):
        assert event.message == event_data.get("message")
    if hasattr(event, "configs"):
        assert len(event.configs) == len(event_data.get("configs", []))


@pytest.mark.asyncio
async def test_run_check_all_success(service):
    expected = MagicMock()
    service.api_adapter.check_all.return_value = expected

    result = await service._run_check_all()

    assert result == expected
    service.api_adapter.check_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_check_all_error(service, monkeypatch):
    service.api_adapter.check_all.side_effect = APIClientError("boom")

    send_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.services.send_to_admins", send_mock)

    result = await service._run_check_all()

    assert result is None
    send_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_user_message_soon(service):
    event = UserNotifyEventSchema(
        type=SubscriptionEventType.USER_NOTIFY,
        user_id=1,
        message="msg",
        subscription_type="premium",
        remaining_days=5,
        active_sbs=True,
    )

    await service._send_user_message(1, "ignored", event)

    service.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_user_message_forbidden(service, monkeypatch):
    event = MagicMock()

    service.bot.send_message.side_effect = TelegramForbiddenError(
        method=None, message="blocked"
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.services.send_to_admins", send_mock)

    await service._send_user_message(1, "msg", event)

    send_mock.assert_awaited_once()


class FakeSSH:
    def __init__(self, host=None, username=None, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def full_delete_user(self, public_key):
        return True


@pytest.mark.asyncio
async def test_delete_from_ssh_success(service):
    cfg = MagicMock(pub_key="key", file_name="file")

    result = await service._delete_from_ssh(cfg, [FakeSSH])

    assert result is True


class FakeSSHFail(FakeSSH):
    def __init__(self, host=None, username=None, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def full_delete_user(self, public_key):
        return False


@pytest.mark.asyncio
async def test_delete_from_ssh_not_found(service):
    cfg = MagicMock(pub_key="key", file_name="file")

    result = await service._delete_from_ssh(cfg, [FakeSSHFail])

    assert result is False


@pytest.mark.asyncio
async def test_fallback_delete_3xui(service):
    cfg = MagicMock(pub_key='["id1","id2"]')

    await service._fallback_delete_3xui(cfg)

    assert service.xray_adapter.delete_config.await_count == 2


@pytest.mark.asyncio
async def test_fallback_delete_3xui_invalid_json(service):
    cfg = MagicMock(pub_key="not_json")

    with pytest.raises(Exception):
        await service._fallback_delete_3xui(cfg)


@pytest.mark.asyncio
async def test_check_all_subscriptions_basic(service, monkeypatch):
    response = CheckAllSubscriptionsResponse(
        stats=SubscriptionStatsSchema(
            checked=10,
            expired=2,
            configs_deleted=0,
        ),
        events=[],
    )

    service.api_adapter.check_all.return_value = response

    send_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.services.send_to_admins", send_mock)

    stats = await service.check_all_subscriptions()

    assert stats.checked == 10
    assert stats.expired == 2
    send_mock.assert_awaited()


@pytest.mark.asyncio
async def test_check_all_with_delete_event(service, monkeypatch):
    cfg = DeletedVPNConfigSchema(file_name="f", pub_key="k")

    event = DeleteVPNConfigsEventSchema(
        type=SubscriptionEventType.DELETE_VPN_CONFIGS,
        user_id=1,
        configs=[cfg],
    )

    response = CheckAllSubscriptionsResponse(
        stats=SubscriptionStatsSchema(checked=1, expired=1, configs_deleted=1),
        events=[event],
    )

    service.api_adapter.check_all.return_value = response
    service._trigger_config_deletion = AsyncMock()

    send_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.services.send_to_admins", send_mock)

    stats = await service.check_all_subscriptions()

    service._trigger_config_deletion.assert_awaited_once()
    assert stats.configs_deleted == 1
