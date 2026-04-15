import pytest
from fastapi import Request
from starlette.datastructures import URL

from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    ReferralBonusAlreadyGivenError,
    ReferralError,
    ReferralNotFoundError,
    SubscriptionNotFoundError,
    TrialAlreadyUsedError,
    UserNotFoundError,
    VPNLimitError,
)
from api.core.exceptions.handlers.business import (
    active_subscription_exists_handler,
    referral_exception_handler,
    subscription_not_found_handler,
    trial_already_used_handler,
    user_not_found_handler,
    vpn_limit_handler,
)


class DummyRequest(Request):
    """Минимальный Request для тестов."""

    def __init__(self, path: str = "/test"):
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
        }
        super().__init__(scope)


@pytest.mark.asyncio
async def test_user_not_found_handler():
    request = DummyRequest("/users")
    exc = UserNotFoundError(tg_id=123)

    response = await user_not_found_handler(request, exc)

    assert response.status_code == 404
    assert response.body
    assert b"telegram_id=123" in response.body


@pytest.mark.asyncio
async def test_subscription_not_found_handler():
    request = DummyRequest("/subscriptions")
    exc = SubscriptionNotFoundError(user_id=42)

    response = await subscription_not_found_handler(request, exc)

    assert response.status_code == 404
    assert b"user_id=42" in response.body


@pytest.mark.asyncio
async def test_active_subscription_exists_handler():
    request = DummyRequest("/subscriptions")
    exc = ActiveSubscriptionExistsError()

    response = await active_subscription_exists_handler(request, exc)

    assert response.status_code == 409
    assert "У пользователя уже есть активная подписка" in response.body.decode()


@pytest.mark.asyncio
async def test_trial_already_used_handler():
    request = DummyRequest("/trial")
    exc = TrialAlreadyUsedError("Trial already used")

    response = await trial_already_used_handler(request, exc)

    assert response.status_code == 409
    assert b"Trial already used" in response.body


@pytest.mark.asyncio
async def test_referral_not_found_handler():
    request = DummyRequest("/referral")
    exc = ReferralNotFoundError("Referral not found")

    response = await referral_exception_handler(request, exc)

    assert response.status_code == 404
    assert b"Referral not found" in response.body


@pytest.mark.asyncio
async def test_referral_bonus_already_given_handler():
    request = DummyRequest("/referral")
    exc = ReferralBonusAlreadyGivenError("Bonus already given")

    response = await referral_exception_handler(request, exc)

    assert response.status_code == 409
    assert b"Bonus already given" in response.body


@pytest.mark.asyncio
async def test_referral_generic_error_handler():
    request = DummyRequest("/referral")
    exc = ReferralError("Generic referral error")

    response = await referral_exception_handler(request, exc)

    assert response.status_code == 400
    assert b"Generic referral error" in response.body


@pytest.mark.asyncio
async def test_vpn_limit_handler():
    request = DummyRequest("/vpn")
    exc = VPNLimitError(user_id=99, limit=5)

    response = await vpn_limit_handler(request, exc)

    assert response.status_code == 409
    assert b"user_id=99" in response.body
    assert b"5" in response.body
    assert b"vpn_limit_reached" in response.body
