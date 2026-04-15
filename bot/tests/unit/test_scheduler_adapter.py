import httpx
import pytest

from bot.integrations.api_client import APIClient
from bot.scheduler.adapter import SchedulerAPIAdapter
from bot.scheduler.schemas import (
    AdminNotifyEventSchema,
    CheckAllSubscriptionsResponse,
    DeletedVPNConfigSchema,
    DeleteProxyEventSchema,
    DeleteVPNConfigsEventSchema,
    SubscriptionStatsSchema,
    UserNotifyEventSchema,
)


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
async def test_check_all_various_events(api_client, event_data, expected_class):
    # Мок-обработчик HTTP-запроса
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

    # Проверка типа и содержимого события
    assert len(response.events) == 1
    event = response.events[0]
    assert isinstance(event, expected_class)

    # Проверяем минимально важные поля
    assert event.user_id == event_data["user_id"]
    if hasattr(event, "message"):
        assert event.message == event_data.get("message")
