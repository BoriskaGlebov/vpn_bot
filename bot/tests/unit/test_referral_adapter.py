import json

import httpx
import pytest

from bot.referrals.adapter import ReferralAPIAdapter
from bot.referrals.schemas import (
    GrantReferralBonusRequest,
    GrantReferralBonusResponse,
    RegisterReferralRequest,
    RegisterReferralResponse,
)


@pytest.mark.asyncio
async def test_register_referral_success(api_client):
    async def handler(request: httpx.Request):
        assert request.url.path == "/api/referrals/register"

        json_data = json.loads(request.content.decode())
        assert json_data == {
            "invited_user_id": 123,
            "inviter_telegram_id": 456,
        }

        return httpx.Response(
            status_code=200,
            json={
                "success": True,
                "message": "Referral registered",
            },
        )

    client = await api_client(handler)
    adapter = ReferralAPIAdapter(client)

    payload = RegisterReferralRequest(
        invited_user_id=123,
        inviter_telegram_id=456,
    )

    result = await adapter.register_referral(payload)

    assert isinstance(result, RegisterReferralResponse)
    assert result.success is True
    assert result.message == "Referral registered"


@pytest.mark.asyncio
async def test_register_referral_without_inviter(api_client):
    async def handler(request: httpx.Request):
        json_data = json.loads(request.content.decode())

        assert json_data == {
            "invited_user_id": 123,
            "inviter_telegram_id": None,
        }

        return httpx.Response(
            status_code=200,
            json={
                "success": True,
                "message": "No inviter",
            },
        )

    client = await api_client(handler)
    adapter = ReferralAPIAdapter(client)

    payload = RegisterReferralRequest(
        invited_user_id=123,
        inviter_telegram_id=None,
    )

    result = await adapter.register_referral(payload)

    assert result.success is True
    assert result.message == "No inviter"


@pytest.mark.asyncio
async def test_grant_bonus_success(api_client):
    async def handler(request: httpx.Request):
        assert request.url.path == "/api/referrals/bonus"

        json_data = json.loads(request.content.decode())
        assert json_data == {
            "invited_user_id": 123,
            "months": 3,
        }

        return httpx.Response(
            status_code=200,
            json={
                "success": True,
                "inviter_telegram_id": 456,
                "message": "Bonus granted",
            },
        )

    client = await api_client(handler)
    adapter = ReferralAPIAdapter(client)

    payload = GrantReferralBonusRequest(
        invited_user_id=123,
        months=3,
    )

    result = await adapter.grant_bonus(payload)

    assert isinstance(result, GrantReferralBonusResponse)
    assert result.success is True
    assert result.inviter_telegram_id == 456
    assert result.message == "Bonus granted"


@pytest.mark.asyncio
async def test_grant_bonus_no_inviter(api_client):
    async def handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            json={
                "success": False,
                "inviter_telegram_id": None,
                "message": "Inviter not found",
            },
        )

    client = await api_client(handler)
    adapter = ReferralAPIAdapter(client)

    payload = GrantReferralBonusRequest(
        invited_user_id=999,
        months=1,
    )

    result = await adapter.grant_bonus(payload)

    assert result.success is False
    assert result.inviter_telegram_id is None
    assert result.message == "Inviter not found"
