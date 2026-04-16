from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.referrals.services import ReferralService
from api.users.schemas import SRoleOut, SUserOut


@pytest.mark.asyncio
async def test_register_referral_success(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    inviter_model = MagicMock()
    inviter_model.id = 1
    inviter_model.telegram_id = 111

    with (
        patch(
            "api.referrals.services.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=inviter_model),
        ),
        patch(
            "api.referrals.services.ReferralDAO.add_referral",
            new=AsyncMock(),
        ) as mock_add_referral,
    ):
        await service.register_referral(
            session=mock_session,
            invited_user=invited_user,
            inviter_telegram_id=111,
        )

        mock_add_referral.assert_awaited_once_with(
            session=mock_session,
            inviter_id=1,
            invited_id=2,
        )


@pytest.mark.asyncio
async def test_register_referral_no_inviter(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    with patch(
        "api.referrals.services.ReferralDAO.add_referral",
        new=AsyncMock(),
    ) as mock_add_referral:
        await service.register_referral(
            session=mock_session,
            invited_user=invited_user,
            inviter_telegram_id=None,
        )

        mock_add_referral.assert_not_called()


@pytest.mark.asyncio
async def test_register_referral_user_used_trial(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=True,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    with patch(
        "api.referrals.services.ReferralDAO.add_referral",
        new=AsyncMock(),
    ) as mock_add_referral:
        await service.register_referral(
            session=mock_session,
            invited_user=invited_user,
            inviter_telegram_id=111,
        )

        mock_add_referral.assert_not_called()


@pytest.mark.asyncio
async def test_register_referral_inviter_not_found(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    with (
        patch(
            "api.referrals.services.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.referrals.services.ReferralDAO.add_referral",
            new=AsyncMock(),
        ) as mock_add_referral,
    ):
        await service.register_referral(
            session=mock_session,
            invited_user=invited_user,
            inviter_telegram_id=111,
        )

        mock_add_referral.assert_not_called()


@pytest.mark.asyncio
async def test_grant_referral_bonus_no_referral(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    with patch(
        "api.referrals.services.ReferralDAO.find_one_or_none",
        new=AsyncMock(return_value=None),
    ):
        result, telegram_id = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
        )

        assert result is False
        assert telegram_id == invited_user.telegram_id


from api.app_error.base_error import ReferralBonusAlreadyGivenError


@pytest.mark.asyncio
async def test_grant_referral_bonus_already_given(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    referral = MagicMock()
    referral.bonus_given = True

    with patch(
        "api.referrals.services.ReferralDAO.find_one_or_none",
        new=AsyncMock(return_value=referral),
    ):
        with pytest.raises(ReferralBonusAlreadyGivenError):
            await service.grant_referral_bonus(
                session=mock_session,
                invited_user=invited_user,
            )


@pytest.mark.asyncio
async def test_grant_referral_bonus_create_subscription(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    inviter = MagicMock()
    inviter.telegram_id = 111
    inviter.current_subscription = None

    referral = MagicMock()
    referral.bonus_given = False
    referral.inviter = inviter

    with (
        patch(
            "api.referrals.services.ReferralDAO.find_one_or_none",
            new=AsyncMock(return_value=referral),
        ),
        patch(
            "api.referrals.services.SubscriptionDAO.activate_subscription",
            new=AsyncMock(),
        ) as mock_activate,
    ):
        result, telegram_id = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
            months=2,
        )

        assert result is True
        assert telegram_id == inviter.telegram_id
        assert referral.bonus_given is True
        assert referral.bonus_given_at is not None
        mock_activate.assert_awaited_once()
        mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_grant_referral_bonus_extend_subscription(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    subscription = MagicMock()
    inviter = MagicMock()
    inviter.telegram_id = 111
    inviter.current_subscription = subscription

    referral = MagicMock()
    referral.bonus_given = False
    referral.inviter = inviter

    with patch(
        "api.referrals.services.ReferralDAO.find_one_or_none",
        new=AsyncMock(return_value=referral),
    ):
        result, telegram_id = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
            months=3,
        )

        assert result is True
        assert telegram_id == inviter.telegram_id
        subscription.extend.assert_called_once_with(months=3)
        assert referral.bonus_given is True
        assert referral.bonus_given_at is not None
        assert mock_session.flush.await_count >= 1


from api.subscription.models import SubscriptionType
from api.users.schemas import SUserTelegramID


@pytest.mark.asyncio
async def test_grant_referral_bonus_activate_subscription_params(mock_session):
    service = ReferralService()

    invited_user = SUserOut(
        id=2,
        telegram_id=222,
        has_used_trial=False,
        username="test",
        first_name="Test",
        last_name="User",
        role=SRoleOut(id=1, name="user", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )

    inviter = MagicMock()
    inviter.telegram_id = 111
    inviter.current_subscription = None

    referral = MagicMock()
    referral.bonus_given = False
    referral.inviter = inviter

    with (
        patch(
            "api.referrals.services.ReferralDAO.find_one_or_none",
            new=AsyncMock(return_value=referral),
        ),
        patch(
            "api.referrals.services.SubscriptionDAO.activate_subscription",
            new=AsyncMock(),
        ) as mock_activate,
    ):
        await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
            months=1,
        )

        mock_activate.assert_awaited_once_with(
            session=mock_session,
            stelegram_id=SUserTelegramID(telegram_id=inviter.telegram_id),
            month=1,
            sub_type=SubscriptionType.STANDARD,
        )
