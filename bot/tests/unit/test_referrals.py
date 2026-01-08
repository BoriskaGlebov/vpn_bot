import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup

from bot.config import settings_bot
from bot.referrals.router import ReferralRouter
from bot.referrals.services import ReferralService


@pytest.fixture
def referral_service(fake_bot, fake_logger):
    return ReferralService(bot=fake_bot, logger=fake_logger)


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_invite_handler_sends_referral_link(
    fake_bot,
    fake_logger,
    make_fake_message,
):
    # Arrange
    message = make_fake_message(user_id=123)

    fake_bot.get_me.return_value.username = "TestBot"

    router = ReferralRouter(
        bot=fake_bot,
        logger=fake_logger,
    )

    # Act
    await router.invite_handler(message)

    # Assert
    fake_bot.get_me.assert_awaited_once()

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args

    # Текст
    assert kwargs["text"] == settings_bot.messages.modes.referrals.invite

    # Клавиатура
    markup = kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)

    button = markup.inline_keyboard[0][0]
    assert "https://t.me/TestBot?start=ref_123" == button.url


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_register_referral_no_inviter_id(
    referral_service,
    session,
):
    invited_user = AsyncMock()
    invited_user.has_used_trial = False

    # Act
    await referral_service.register_referral(
        session=session,
        invited_user=invited_user,
        inviter_telegram_id=None,
    )

    # Assert — ничего не вызывается
    # (ошибка тут = тест упадёт сам)


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_register_referral_success(
    referral_service,
    session,
    monkeypatch,
):
    invited_user = AsyncMock()
    invited_user.id = 10
    invited_user.has_used_trial = False

    inviter_model = AsyncMock()
    inviter_model.id = 5

    find_user = AsyncMock(return_value=inviter_model)
    add_referral = AsyncMock()

    monkeypatch.setattr(
        "bot.referrals.services.UserDAO.find_one_or_none",
        find_user,
    )
    monkeypatch.setattr(
        "bot.referrals.services.ReferralDAO.add_referral",
        add_referral,
    )

    # Act
    await referral_service.register_referral(
        session=session,
        invited_user=invited_user,
        inviter_telegram_id=123,
    )

    # Assert
    find_user.assert_awaited_once()
    add_referral.assert_awaited_once_with(
        session=session,
        inviter_id=5,
        invited_id=10,
    )


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_no_referral(
    referral_service,
    session,
    monkeypatch,
):
    invited_user = AsyncMock()
    invited_user.id = 10
    invited_user.telegram_id = 999

    monkeypatch.setattr(
        "bot.referrals.services.ReferralDAO.find_one_or_none",
        AsyncMock(return_value=None),
    )

    result, inviter_id = await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_user,
    )

    assert result is False
    assert inviter_id is None


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_success_with_existing_subscription(
    referral_service,
    session,
    monkeypatch,
):
    invited_user = AsyncMock()
    invited_user.id = 10
    invited_user.telegram_id = 999

    current_sub = AsyncMock()
    current_sub.extend = AsyncMock()

    inviter = AsyncMock()
    inviter.telegram_id = 123
    inviter.current_subscription = current_sub

    referral = AsyncMock()
    referral.bonus_given = False
    referral.inviter = inviter

    monkeypatch.setattr(
        "bot.referrals.services.ReferralDAO.find_one_or_none",
        AsyncMock(return_value=referral),
    )

    # Act
    result, inviter_id = await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_user,
        months=2,
    )

    # Assert
    assert result is True
    assert inviter_id == 123

    current_sub.extend.assert_awaited_once_with(months=2)
    assert referral.bonus_given is True
    assert isinstance(referral.bonus_given_at, datetime.datetime)


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_success_with_existing_subscription(
    referral_service,
    session,
    monkeypatch,
):
    invited_user = AsyncMock()
    invited_user.id = 10
    invited_user.telegram_id = 999

    current_sub = MagicMock()
    current_sub.extend = MagicMock()

    inviter = AsyncMock()
    inviter.telegram_id = 123
    inviter.current_subscription = current_sub

    referral = AsyncMock()
    referral.bonus_given = False
    referral.inviter = inviter

    monkeypatch.setattr(
        "bot.referrals.services.ReferralDAO.find_one_or_none",
        AsyncMock(return_value=referral),
    )

    # Act
    result, inviter_id = await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_user,
        months=2,
    )

    # Assert
    assert result is True
    assert inviter_id == 123

    current_sub.extend.assert_called_once_with(months=2)
    assert referral.bonus_given is True
    assert isinstance(referral.bonus_given_at, datetime.datetime)


@pytest.mark.asyncio
@pytest.mark.referrals
async def test_grant_referral_bonus_creates_subscription(
    referral_service,
    session,
    monkeypatch,
):
    invited_user = AsyncMock()
    invited_user.id = 10
    invited_user.telegram_id = 999

    inviter = AsyncMock()
    inviter.telegram_id = 123
    inviter.current_subscription = None

    referral = AsyncMock()
    referral.bonus_given = False
    referral.inviter = inviter

    monkeypatch.setattr(
        "bot.referrals.services.ReferralDAO.find_one_or_none",
        AsyncMock(return_value=referral),
    )

    activate_sub = AsyncMock()
    monkeypatch.setattr(
        "bot.referrals.services.SubscriptionDAO.activate_subscription",
        activate_sub,
    )

    await referral_service.grant_referral_bonus(
        session=session,
        invited_user=invited_user,
    )

    activate_sub.assert_awaited_once()
