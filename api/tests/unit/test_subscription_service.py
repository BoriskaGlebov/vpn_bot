from unittest.mock import AsyncMock, MagicMock

import pytest

from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    TrialAlreadyUsedError,
    UserNotFoundError,
)
from api.subscription.dao import SubscriptionDAO
from api.subscription.models import Subscription, SubscriptionType
from api.subscription.services import SubscriptionService
from api.users.models import User
from shared.enums.admin_enum import RoleEnum


@pytest.fixture
def user():
    user = MagicMock(spec=User)
    user.id = 1
    user.telegram_id = 123
    user.role.name = RoleEnum.USER
    user.has_used_trial = False

    sub = MagicMock(spec=Subscription)
    sub.is_active = True
    sub.type = SubscriptionType.STANDARD
    sub.extend = MagicMock()

    user.current_subscription = sub
    user.subscriptions = [sub]
    user.vpn_configs = []
    return user


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def mock_user_dao(user):
    return AsyncMock(return_value=user)


@pytest.fixture
def mock_subscription_dao():
    return AsyncMock()


@pytest.mark.asyncio
async def test_check_premium_true(user, session, monkeypatch):
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService.check_premium(session, tg_id=123)

    assert result[0] is False  # STANDARD в фикстуре
    assert result[1] is not None


@pytest.mark.asyncio
async def test_check_premium_user_not_found(session, monkeypatch):
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=None),
    )

    with pytest.raises(UserNotFoundError):
        await SubscriptionService.check_premium(session, tg_id=123)


@pytest.mark.asyncio
async def test_start_trial_extend(user, session, monkeypatch):
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    await SubscriptionService.start_trial_subscription(session, tg_id=123, days=10)

    user.current_subscription.extend.assert_called_once_with(days=10)
    assert user.has_used_trial is True


@pytest.mark.asyncio
async def test_start_trial_already_used(user, session, monkeypatch):
    user.has_used_trial = True

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    with pytest.raises(ActiveSubscriptionExistsError):
        await SubscriptionService.start_trial_subscription(session, tg_id=123, days=10)


@pytest.mark.asyncio
async def test_start_trial_create_new(session, monkeypatch):
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        "api.subscription.services.SubscriptionDAO.activate_subscription",
        AsyncMock(return_value=MagicMock()),
    )

    await SubscriptionService.start_trial_subscription(session, tg_id=123, days=10)

    SubscriptionDAO.activate_subscription.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_paid_extend(user, session, monkeypatch):
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    user.subscriptions = [user.current_subscription]

    result = await SubscriptionService.activate_paid_subscription(
        session, user_id=123, months=3, premium=False
    )

    user.current_subscription.extend.assert_called_once_with(months=3)
    assert result is not None


@pytest.mark.asyncio
async def test_activate_paid_founder(user, session, monkeypatch):
    user.role.name = RoleEnum.FOUNDER

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService.activate_paid_subscription(
        session, user_id=123, months=3, premium=True
    )

    assert result is not None


@pytest.mark.asyncio
async def test_activate_paid_create(session, monkeypatch):
    user = MagicMock()
    user.subscriptions = []
    user.role.name = RoleEnum.USER
    user.current_subscription = None

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    mock_dao = AsyncMock()
    monkeypatch.setattr(
        "api.subscription.services.SubscriptionDAO.activate_subscription",
        mock_dao,
    )

    monkeypatch.setattr(
        "api.subscription.services.UserMapper.to_schema",
        AsyncMock(return_value={"ok": True}),
    )

    result = await SubscriptionService.activate_paid_subscription(
        session, user_id=123, months=3, premium=False
    )

    mock_dao.assert_awaited_once()
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_get_subscription_info(user, session, monkeypatch):
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService().get_subscription_info(session, 123)

    assert result.status == "active"
    assert result.subscription_type is not None


@pytest.mark.asyncio
async def test_get_subscription_info_empty(session, monkeypatch):
    user = MagicMock()
    user.current_subscription = None
    user.vpn_configs = []

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService().get_subscription_info(session, 123)

    assert result.status == "no_subscription"
