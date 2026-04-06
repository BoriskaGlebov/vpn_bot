import json
from datetime import datetime

import httpx
import pytest

from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateResponse,
)


@pytest.mark.asyncio
async def test_check_limit(api_client):
    async def handler(request):
        assert request.url.path == "/api/vpn/limit"
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
        assert request.url.path == "/api/vpn/config"
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
