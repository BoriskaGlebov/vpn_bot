from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from api.app_error.base_error import (
    AppError,
    TrialAlreadyUsedError,
    UserNotFoundError,
)
from api.subscription.dao import SubscriptionDAO
from api.subscription.models import Subscription, SubscriptionType
from api.users.schemas import SUserTelegramID


@pytest.fixture
def telegram_id():
    return SUserTelegramID(telegram_id=123456789)


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    return user


@pytest.fixture
def mock_subscription():
    sub = MagicMock(spec=Subscription)
    sub.activate = MagicMock()
    return sub


@pytest.fixture
def session():
    return AsyncMock()


# -------------------------
# SUCCESS CASE
# -------------------------
@pytest.mark.asyncio
async def test_activate_subscription_success(
    telegram_id,
    mock_user,
    mock_subscription,
    session,
):
    with (
        patch(
            "api.subscription.dao.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=mock_user),
        ) as mock_find_user,
        patch(
            "api.subscription.dao.SubscriptionDAO.add",
            new=AsyncMock(return_value=mock_subscription),
        ) as mock_add,
    ):

        result = await SubscriptionDAO.activate_subscription(
            session=session,
            stelegram_id=telegram_id,
            days=10,
            month=1,
            sub_type=SubscriptionType.STANDARD,
        )

        assert result == mock_subscription

        mock_find_user.assert_awaited_once()
        mock_add.assert_awaited_once()

        session.flush.assert_awaited_once()
        mock_subscription.activate.assert_called_once_with(
            days=10,
            month_num=1,
            sub_type=SubscriptionType.STANDARD,
        )


# -------------------------
# USER NOT FOUND
# -------------------------
@pytest.mark.asyncio
async def test_activate_subscription_user_not_found(
    telegram_id,
    session,
):
    with patch(
        "api.subscription.dao.UserDAO.find_one_or_none",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(UserNotFoundError):
            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=telegram_id,
                days=10,
            )


# -------------------------
# TRIAL / APP ERROR PROPAGATION
# -------------------------
@pytest.mark.asyncio
async def test_activate_subscription_app_error_propagation(
    telegram_id,
    mock_user,
    session,
):
    mock_subscription = MagicMock(spec=Subscription)
    mock_subscription.activate.side_effect = TrialAlreadyUsedError()

    with (
        patch(
            "api.subscription.dao.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=mock_user),
        ),
        patch(
            "api.subscription.dao.SubscriptionDAO.add",
            new=AsyncMock(return_value=mock_subscription),
        ),
    ):

        with pytest.raises(TrialAlreadyUsedError):
            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=telegram_id,
                days=5,
            )


# -------------------------
# SQLA ERROR CASE
# -------------------------
@pytest.mark.asyncio
async def test_activate_subscription_sqlalchemy_error(
    telegram_id,
    mock_user,
    session,
):
    mock_subscription = MagicMock(spec=Subscription)
    mock_subscription.activate.return_value = None

    with (
        patch(
            "api.subscription.dao.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=mock_user),
        ),
        patch(
            "api.subscription.dao.SubscriptionDAO.add",
            new=AsyncMock(return_value=mock_subscription),
        ),
        patch(
            "api.subscription.dao.SubscriptionDAO.add",
            new=AsyncMock(side_effect=SQLAlchemyError("db fail")),
        ),
    ):

        with pytest.raises(SQLAlchemyError):
            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=telegram_id,
                days=5,
            )
