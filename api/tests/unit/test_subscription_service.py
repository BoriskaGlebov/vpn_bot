from unittest.mock import AsyncMock, MagicMock

import pytest

from api.app_error.base_error import (
    TrialAlreadyUsedError,
    UserNotFoundError,
)
from api.subscription.models import Subscription, SubscriptionType
from api.subscription.services import SubscriptionService
from api.users.models import User
from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import TrialStatus


@pytest.fixture
def user():
    user = MagicMock(spec=User)
    user.username = "test_user"
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
    """STANDARD-подписка -> premium=False, но роль пользователя присутствует в ответе."""
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService.check_premium(session, tg_id=123)

    assert result.premium is False  # STANDARD в фикстуре
    assert result.role is not None


@pytest.mark.asyncio
async def test_check_premium_user_not_found(session, monkeypatch):
    """Пользователь не найден -> UserNotFoundError."""
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=None),
    )

    with pytest.raises(UserNotFoundError):
        await SubscriptionService.check_premium(session, tg_id=123)


@pytest.mark.asyncio
async def test_start_trial_extend(user, session, monkeypatch):
    """У пользователя уже есть подписка -> триал продлевает её и ставит has_used_trial."""
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService.start_trial_subscription(
        session, tg_id=123, days=10
    )

    user.current_subscription.extend.assert_called_once_with(days=10)
    assert user.has_used_trial is True
    # #283: продление отвечает EXTENDED, а не тем же значением, что создание.
    assert result == TrialStatus.EXTENDED


@pytest.mark.asyncio
async def test_start_trial_already_used(user, session, monkeypatch):
    """Триал уже был использован -> TrialAlreadyUsedError."""
    user.has_used_trial = True

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    with pytest.raises(TrialAlreadyUsedError):
        await SubscriptionService.start_trial_subscription(session, tg_id=123, days=10)


@pytest.mark.asyncio
async def test_start_trial_create_new(session, monkeypatch):
    """У пользователя ещё нет подписки -> триал создаёт новую через activate_subscription."""
    user = MagicMock()
    user.id = 1
    user.username = "test"
    user.current_subscription = None
    user.has_used_trial = False

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    activate_mock = AsyncMock()

    monkeypatch.setattr(
        "api.subscription.services.SubscriptionDAO.activate_subscription",
        activate_mock,
    )

    result = await SubscriptionService.start_trial_subscription(
        session,
        tg_id=123,
        days=10,
    )

    activate_mock.assert_awaited_once()
    assert user.has_used_trial is True
    # #283: Subscription.activate() больше не выставляет has_used_trial сам —
    # это делает сервис; создание (в отличие от продления) отвечает STARTED.
    assert result == TrialStatus.STARTED

    session.refresh.assert_awaited_once_with(
        user,
        attribute_names=["subscriptions", "role", "vpn_configs"],
    )


@pytest.mark.asyncio
async def test_activate_paid_extend(user, session, monkeypatch):
    """Есть активная подписка -> платная активация продлевает её."""
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    user.subscriptions = [user.current_subscription]

    result = await SubscriptionService.activate_paid_subscription(
        session, tg_id=123, months=3, premium=False
    )

    user.current_subscription.extend.assert_called_once_with(months=3)
    assert result is not None


@pytest.mark.asyncio
async def test_activate_paid_founder(user, session, monkeypatch):
    """FOUNDER-роль допускает платную активацию так же, как обычный пользователь."""
    user.role.name = RoleEnum.FOUNDER

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService.activate_paid_subscription(
        session, tg_id=123, months=3, premium=True
    )

    assert result is not None


@pytest.mark.asyncio
async def test_activate_paid_create(session, monkeypatch):
    """У пользователя нет подписки -> платная активация создаёт новую через DAO."""
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
        MagicMock(return_value={"ok": True}),
    )

    result = await SubscriptionService.activate_paid_subscription(
        session, tg_id=123, months=3, premium=False
    )

    mock_dao.assert_awaited_once()
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_activate_paid_create_deactivates_other_active_type(session, monkeypatch):
    """Активная подписка ДРУГОГО типа (например, TRIAL) не попадает в поиск по
    sub_type и раньше оставалась брошенной is_active=True (#275) — теперь
    деактивируется явно перед созданием новой платной подписки.
    """
    user = MagicMock()
    user.role.name = RoleEnum.USER

    abandoned_trial = MagicMock(spec=Subscription)
    abandoned_trial.is_active = True
    abandoned_trial.type = SubscriptionType.TRIAL
    abandoned_trial.deactivate = MagicMock()

    user.subscriptions = [abandoned_trial]
    user.current_subscription = abandoned_trial

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
        MagicMock(return_value={"ok": True}),
    )

    await SubscriptionService.activate_paid_subscription(
        session, tg_id=123, months=3, premium=False
    )

    abandoned_trial.deactivate.assert_called_once()
    mock_dao.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_subscription_info(user, session, monkeypatch):
    """Пользователь с активной подпиской -> status='active'."""
    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService().get_subscription_info(session, 123)

    assert result.status == "active"
    assert result.subscription_type is not None


@pytest.mark.asyncio
async def test_get_subscription_info_empty(session, monkeypatch):
    """Пользователь без подписки -> status='no_subscription'."""
    user = MagicMock()
    user.current_subscription = None
    user.vpn_configs = []

    monkeypatch.setattr(
        "api.subscription.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    result = await SubscriptionService().get_subscription_info(session, 123)

    assert result.status == "no_subscription"
