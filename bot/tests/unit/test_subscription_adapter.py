import json

import httpx
import pytest

from bot.subscription.adapter import SubscriptionAPIAdapter
from bot.subscription.schemas import (
    SSubscriptionCheck,
    STrialActivateResponse,
)
from bot.users.schemas import SUserOut
from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import TrialStatus


@pytest.mark.asyncio
async def test_check_premium(api_client):
    async def handler(request):
        assert request.url.path == "/subscriptions/check/premium"
        assert request.url.params["tg_id"] == "123"

        return httpx.Response(
            status_code=200,
            json={
                "premium": True,
                "role": RoleEnum.USER.value,
                "is_active": True,
            },
        )

    client = await api_client(handler)
    adapter = SubscriptionAPIAdapter(client)

    result = await adapter.check_premium(123)

    assert isinstance(result, SSubscriptionCheck)
    assert result.premium is True
    assert result.role == RoleEnum.USER
    assert result.is_active is True


@pytest.mark.asyncio
async def test_activate_trial(api_client):
    async def handler(request):
        assert request.url.path == "/subscriptions/trial/activate"

        payload = json.loads(request.content.decode())
        assert payload["tg_id"] == 123
        assert payload["days"] == 7

        return httpx.Response(
            status_code=201,
            json={"status": TrialStatus.STARTED.value},
        )

    client = await api_client(handler)
    adapter = SubscriptionAPIAdapter(client)

    result, status = await adapter.activate_trial(123, days=7)

    assert isinstance(result, STrialActivateResponse)
    assert result.status == TrialStatus.STARTED
    assert status == 201


@pytest.mark.asyncio
async def test_activate_paid(api_client, user_out):
    async def handler(request):
        assert request.url.path == "/subscriptions/activate"

        payload = json.loads(request.content.decode())
        assert payload["tg_id"] == 123
        assert payload["months"] == 3
        assert payload["premium"] is True

        return httpx.Response(
            status_code=200,
            json=user_out.model_dump(mode="json"),
        )

    client = await api_client(handler)
    adapter = SubscriptionAPIAdapter(client)

    result = await adapter.activate_paid(
        tg_id=123,
        months=3,
        premium=True,
    )

    assert isinstance(result, SUserOut)

    # сравнение через модель (самый надежный способ)
    assert result.model_dump(mode="json") == user_out.model_dump(mode="json")
