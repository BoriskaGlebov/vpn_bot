import pytest

from bot.referrals.schemas import GrantReferralBonusRequest, RegisterReferralRequest
from bot.referrals.services import ReferralService
from bot.users.schemas import SUserOut


@pytest.fixture
def user_out_trial_true(role_out, subscription_out):
    return SUserOut(
        id=1,
        telegram_id=123456,
        username="test_user",
        first_name="John",
        last_name="Doe",
        has_used_trial=True,
        role=role_out,
        subscriptions=[subscription_out],
        vpn_configs=[],
        current_subscription=subscription_out,
    )


@pytest.mark.asyncio
async def test_register_referral_called(mock_referral_adapter, user_out):
    service = ReferralService(adapter=mock_referral_adapter)
    user = user_out

    await service.register_referral(user, inviter_telegram_id=456)

    # Проверяем, что адаптер вызвался с правильным payload
    mock_referral_adapter.register_referral.assert_awaited_once()
    args, _ = mock_referral_adapter.register_referral.call_args
    payload = args[0]
    assert isinstance(payload, RegisterReferralRequest)
    assert payload.invited_user_id == 123456
    assert payload.inviter_telegram_id == 456


@pytest.mark.asyncio
async def test_register_referral_skipped_if_no_inviter(mock_referral_adapter, user_out):
    service = ReferralService(adapter=mock_referral_adapter)
    user = user_out

    await service.register_referral(user, inviter_telegram_id=None)

    # Адаптер не должен вызываться
    mock_referral_adapter.register_referral.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_referral_skipped_if_used_trial(
    mock_referral_adapter, user_out_trial_true
):
    service = ReferralService(adapter=mock_referral_adapter)
    user = user_out_trial_true

    await service.register_referral(invited_user=user, inviter_telegram_id=456)

    # Адаптер не должен вызываться
    mock_referral_adapter.register_referral.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_referral_bonus_success(mock_referral_adapter, user_out):
    # Мок адаптера возвращает успешный ответ
    mock_referral_adapter.grant_bonus.return_value.success = True
    mock_referral_adapter.grant_bonus.return_value.inviter_telegram_id = 456

    service = ReferralService(adapter=mock_referral_adapter)
    user = user_out

    success, inviter_id = await service.grant_referral_bonus(user, months=3)

    assert success is True
    assert inviter_id == 456

    mock_referral_adapter.grant_bonus.assert_awaited_once()
    args, _ = mock_referral_adapter.grant_bonus.call_args
    payload = args[0]
    assert isinstance(payload, GrantReferralBonusRequest)
    assert payload.invited_user_id == 123456
    assert payload.months == 3


@pytest.mark.asyncio
async def test_grant_referral_bonus_failed(mock_referral_adapter, user_out):
    # Мок адаптера возвращает неуспешный ответ
    mock_referral_adapter.grant_bonus.return_value.success = False
    mock_referral_adapter.grant_bonus.return_value.inviter_telegram_id = None

    service = ReferralService(adapter=mock_referral_adapter)
    user = user_out

    success, inviter_id = await service.grant_referral_bonus(user, months=1)

    assert success is False
    assert inviter_id is None
    mock_referral_adapter.grant_bonus.assert_awaited_once()
