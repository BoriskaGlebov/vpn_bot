import json
from datetime import datetime

import httpx
import pytest

from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateResponse,
    SVPNSubscriptionInfo,
)


@pytest.mark.asyncio
async def test_check_limit(api_client):
    async def handler(request):
        assert request.url.path == "/vpn/limit"
        assert request.method == "GET"
        assert request.url.params["tg_id"] == "123"

        return httpx.Response(
            status_code=200,
            json={
                "can_add": True,
                "limit": 5,
                "current": 2,
            },
        )

    client = await api_client(handler)
    adapter = VPNAPIAdapter(client)

    result = await adapter.check_limit(tg_id=123)

    assert isinstance(result, SVPNCheckLimitResponse)
    assert result.can_add is True
    assert result.limit == 5
    assert result.current == 2


@pytest.mark.asyncio
async def test_add_config(api_client):
    async def handler(request):
        assert request.url.path == "/vpn/config"
        assert request.method == "POST"

        body = json.loads(request.content)
        assert body == {
            "tg_id": 123,
            "file_name": "test.conf",
            "pub_key": "pubkey123",
        }

        return httpx.Response(
            status_code=200,
            json={
                "file_name": "test.conf",
                "pub_key": "pubkey123",
            },
        )

    client = await api_client(handler)
    adapter = VPNAPIAdapter(client)

    result = await adapter.add_config(
        tg_id=123,
        file_name="test.conf",
        pub_key="pubkey123",
    )

    assert isinstance(result, SVPNCreateResponse)
    assert result.file_name == "test.conf"
    assert result.pub_key == "pubkey123"


@pytest.mark.asyncio
async def test_get_subscription_info(api_client):
    async def handler(request):
        assert request.url.path == "/vpn/subscription"
        assert request.method == "GET"
        assert request.url.params["tg_id"] == "123"

        return httpx.Response(
            status_code=200,
            json={
                "status": "active",
                "subscription_type": "PREMIUM",
                "remaining": "10",
                "configs": [
                    {"file_name": "config1.conf"},
                    {"file_name": "config2.conf"},
                ],
                "end_date": "2026-01-01",
            },
        )

    client = await api_client(handler)
    adapter = VPNAPIAdapter(client)

    result = await adapter.get_subscription_info(tg_id=123)

    assert isinstance(result, SVPNSubscriptionInfo)
    assert result.status == "active"
    assert result.subscription_type == "PREMIUM"
    assert result.remaining == "10"
    assert len(result.configs) == 2
    assert result.configs[0].file_name == "config1.conf"
    assert result.end_date == datetime(2026, 1, 1)
