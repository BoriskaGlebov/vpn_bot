"""Тесты ReferralService: регистрация реферала и начисление бонуса пригласившему."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.referrals.services import ReferralService
from api.subscription.models import SubscriptionType
from api.users.schemas import SRoleOut, SUserOut, SUserTelegramID


def make_invited_user(**overrides) -> SUserOut:
    """SUserOut приглашённого пользователя с полями по умолчанию."""
    defaults = dict(
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
    defaults.update(overrides)
    return SUserOut(**defaults)


@pytest.mark.asyncio
async def test_register_referral_success(mock_session):
    """Инвайтер найден по telegram_id -> запись Referral создаётся с его id."""
    service = ReferralService()
    invited_user = make_invited_user()

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
    """inviter_telegram_id не передан -> реферал не регистрируется."""
    service = ReferralService()
    invited_user = make_invited_user()

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
    """Приглашённый уже использовал триал -> реферал не регистрируется повторно."""
    service = ReferralService()
    invited_user = make_invited_user(has_used_trial=True)

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
async def test_register_referral_self_referral_rejected(mock_session):
    """inviter_telegram_id == telegram_id приглашённого -> реферал не регистрируется.

    api/ — единственная точка, реально пишущая в БД, поэтому не должна
    полагаться на то, что вызывающая сторона (bot/, см. проверку в
    bot/users/router.py) никогда не пришлёт такой запрос напрямую.
    """
    service = ReferralService()
    invited_user = make_invited_user(telegram_id=111)

    with (
        patch(
            "api.referrals.services.UserDAO.find_one_or_none",
            new=AsyncMock(),
        ) as mock_find_inviter,
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

        mock_find_inviter.assert_not_called()
        mock_add_referral.assert_not_called()


@pytest.mark.asyncio
async def test_register_referral_inviter_not_found(mock_session):
    """Инвайтер с указанным telegram_id не найден -> реферал не регистрируется."""
    service = ReferralService()
    invited_user = make_invited_user()

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
    """Для приглашённого нет записи Referral -> бонус не начисляется."""
    service = ReferralService()
    invited_user = make_invited_user()

    with patch(
        "api.referrals.services.ReferralDAO.find_one_or_none",
        new=AsyncMock(return_value=None),
    ):
        result, telegram_id, message = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
        )

        assert result is False
        assert telegram_id == invited_user.telegram_id
        assert message == f"У пользователя не было приглашения {telegram_id}"


@pytest.mark.asyncio
async def test_grant_referral_bonus_already_given(mock_session):
    """Бонус за этого приглашённого уже был начислен ранее -> повторно не начисляется."""
    service = ReferralService()
    invited_user = make_invited_user()

    inviter = MagicMock()
    inviter.telegram_id = 111

    referral = MagicMock()
    referral.bonus_given = True
    referral.inviter = inviter

    with patch(
        "api.referrals.services.ReferralDAO.find_one_or_none",
        new=AsyncMock(return_value=referral),
    ):
        result, telegram_id, message = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
        )

        assert result is False
        assert telegram_id == 111
        assert message == "Бонус за друга уже начислен пользователю 111"

        mock_session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_referral_bonus_create_subscription(mock_session):
    """У инвайтера нет активной подписки -> создаётся новая через activate_subscription."""
    service = ReferralService()
    invited_user = make_invited_user()

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
        result, telegram_id, message = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
            months=2,
        )

        assert result is True
        assert telegram_id == inviter.telegram_id
        assert (
            message
            == "Бонус за подписчика предоставлен: inviter=111, invited=222, months=2"
        )
        assert referral.bonus_given is True
        assert referral.bonus_given_at is not None
        mock_activate.assert_awaited_once()
        mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_grant_referral_bonus_extend_subscription(mock_session):
    """У инвайтера уже есть подписка -> она продлевается, а не создаётся новая."""
    service = ReferralService()
    invited_user = make_invited_user()

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
        result, telegram_id, message = await service.grant_referral_bonus(
            session=mock_session,
            invited_user=invited_user,
            months=3,
        )

        assert result is True
        assert telegram_id == inviter.telegram_id
        assert (
            message
            == "Бонус за подписчика предоставлен: inviter=111, invited=222, months=3"
        )
        subscription.extend.assert_called_once_with(months=3)
        assert referral.bonus_given is True
        assert referral.bonus_given_at is not None
        assert mock_session.flush.await_count >= 1


@pytest.mark.asyncio
async def test_grant_referral_bonus_activate_subscription_params(mock_session):
    """Новая подписка инвайтеру создаётся с правильным типом (STANDARD) и сроком."""
    service = ReferralService()
    invited_user = make_invited_user()

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
