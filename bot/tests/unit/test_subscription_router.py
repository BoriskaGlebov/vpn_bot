from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.types import ReplyKeyboardRemove

from bot.subscription.router import SubscriptionRouter, SubscriptionStates
from shared.enums.admin_enum import FilterTypeEnum


@pytest.mark.asyncio
async def test_start_subscription_premium_user(
    mocker,
    fake_bot,
    make_fake_message,
    fake_state,
):
    bot_mock = fake_bot
    message_mock = make_fake_message()
    state_mock = fake_state
    user = mocker.Mock(id=123, username="testuser")

    service_mock = mocker.AsyncMock()
    service_mock.check_premium.return_value = (True, FilterTypeEnum.USER, True)

    router = SubscriptionRouter(
        bot=bot_mock,
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
    )

    await router.start_subscription(message=message_mock, state=state_mock)

    service_mock.check_premium.assert_awaited_once_with(tg_id=123)
    message_mock.answer.assert_any_call(
        text="Начнем оформление подписки", reply_markup=ReplyKeyboardRemove()
    )
    state_mock.set_state.assert_awaited_once_with(SubscriptionStates.subscription_start)


@pytest.mark.asyncio
async def test_subscription_selected_paid(mocker):
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock  # ключевой момент
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"premium": True}
    callback_data = Mock(months=3)

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=mocker.AsyncMock(),
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
    )

    await router.subscription_selected(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    query_mock.answer.assert_awaited()
    msg_mock.edit_text.assert_awaited()
    state_mock.set_state.assert_awaited_with(SubscriptionStates.select_period)


from bot.core.config import settings_bot


@pytest.mark.asyncio
async def test_user_paid_calls_admins(
    mocker, fake_bot, fake_logger, fake_redis_service
):
    bot_mock = fake_bot
    msg_mock = mocker.AsyncMock()
    query_mock = mocker.AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = mocker.Mock(id=123, username="user")
    callback_data = mocker.Mock(months=2)

    # Мок price_map
    mocker.patch.object(settings_bot, "price_map", {2: 100, 3: 150})

    router = SubscriptionRouter(
        bot=bot_mock,
        logger=fake_logger,
        subscription_service=mocker.AsyncMock(),
        referral_service=mocker.AsyncMock(),
        redis_service=fake_redis_service,
    )

    send_to_admins_mock = mocker.patch("bot.subscription.router.send_to_admins")

    state_mock = mocker.AsyncMock()
    state_mock.get_data.return_value = {"premium": True}

    await router.user_paid(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    send_to_admins_mock.assert_awaited_once()
    query_mock.answer.assert_awaited()
    msg_mock.edit_text.assert_awaited()


from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.asyncio
async def test_admin_confirm_payment(mocker):
    # --- mocks ---
    bot_mock = AsyncMock()

    msg_mock = AsyncMock()
    msg_mock.chat.id = 999  # важно для ChatActionSender

    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=999, username="admin")

    callback_data = Mock(user_id=1, months=3, premium=True)

    # user_schema должен иметь нужные поля
    user_schema = Mock(
        username="user",
        first_name="John",
        last_name="Doe",
        telegram_id=1,
    )

    subscription_service_mock = AsyncMock()
    subscription_service_mock.activate_paid_subscription.return_value = user_schema

    referral_service_mock = AsyncMock()
    referral_service_mock.grant_referral_bonus.return_value = (False, None)

    redis_mock = AsyncMock()

    router = SubscriptionRouter(
        bot=bot_mock,
        logger=Mock(),
        subscription_service=subscription_service_mock,
        referral_service=referral_service_mock,
        redis_service=redis_mock,
    )

    # --- правильные patch ---
    mocker.patch("bot.subscription.router.edit_admin_messages")

    # --- run ---
    await router.admin_confirm_payment(
        query=query_mock,
        state=AsyncMock(),
        callback_data=callback_data,
    )

    # --- asserts ---
    subscription_service_mock.activate_paid_subscription.assert_awaited_once_with(
        1, 3, True
    )

    bot_mock.send_message.assert_awaited()  # пользователю отправлено сообщение

    referral_service_mock.grant_referral_bonus.assert_awaited_once_with(
        invited_user=user_schema
    )

    query_mock.answer.assert_awaited()

    subscription_service_mock.activate_paid_subscription.assert_awaited_once_with(
        1, 3, True
    )
    bot_mock.send_message.assert_awaited()
