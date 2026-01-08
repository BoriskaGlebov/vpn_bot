import datetime

import pytest
from sqlalchemy import select

from bot.users.schemas import SUserOut


@pytest.fixture
def referral_service(fake_bot, fake_logger):
    from bot.referrals.services import ReferralService

    return ReferralService(
        bot=fake_bot,
        logger=fake_logger,
    )


@pytest.fixture
async def create_referral(session, setup_users):
    inviter, _, invited, _ = setup_users

    from bot.referrals.models import Referral

    referral = Referral(
        inviter_id=inviter.id,
        invited_id=invited.id,
        bonus_given=False,
    )
    session.add(referral)
    await session.commit()
    await session.refresh(referral)

    return referral


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_success_existing_subscription(
    referral_service,
    session,
    setup_users,
    create_referral,
):
    # Arrange
    _, _, invited_user, _ = setup_users

    invited_schema = SUserOut.model_validate(invited_user)

    # Act
    result, inviter_telegram_id = await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_schema,
        months=2,
    )

    # Assert
    assert result is True
    assert inviter_telegram_id == setup_users[0].telegram_id

    await session.refresh(create_referral)
    assert create_referral.bonus_given is True
    assert create_referral.bonus_given_at is not None


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_no_referral(
    referral_service,
    session,
    setup_users,
):
    invited_user = setup_users[2]

    invited_schema = SUserOut.model_validate(invited_user)

    result, inviter_id = await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_schema,
    )

    assert result is False
    assert inviter_id is None


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_already_given(
    referral_service,
    session,
    create_referral,
    setup_users,
):
    inviter, _, invited, _ = setup_users

    referral = create_referral
    referral.bonus_given = True
    await session.commit()

    invited_schema = SUserOut.model_validate(invited)

    result, inviter_id = await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_schema,
    )

    assert result is False
    assert inviter_id is None


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_register_referral_success(
    referral_service,
    session,
    setup_users,
):
    inviter, _, invited, _ = setup_users

    invited_schema = SUserOut.model_validate(invited)

    await referral_service.register_referral(
        session=session,
        invited_user=invited_schema,
        inviter_telegram_id=inviter.telegram_id,
    )

    from bot.referrals.models import Referral

    referral = await session.scalar(
        select(Referral).where(Referral.invited_id == invited.id)
    )

    assert referral is not None
    assert referral.inviter_id == inviter.id
    assert referral.bonus_given is False
