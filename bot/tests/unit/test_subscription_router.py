from unittest.mock import AsyncMock, Mock
from uuid import UUID

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
    service_mock.check_premium.return_value = (True, FilterTypeEnum.USER, True, True)

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
    callback_data = Mock(months=3, founder=False)

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
    payment_adapter_mock = mocker.AsyncMock()
    payment_adapter_mock.create_transaction.return_value = mocker.Mock(
        id=UUID("12345678-1234-5678-1234-567812345678")
    )
    subscription_service = mocker.AsyncMock()
    subscription_service = mocker.AsyncMock()
    subscription_service.payment_adapter = payment_adapter_mock

    bot_mock = fake_bot
    msg_mock = mocker.AsyncMock()
    query_mock = mocker.AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = mocker.Mock(id=123, username="user")
    callback_data = mocker.Mock(
        months=3,
        founder=False,
        transaction_id=UUID("12345678-1234-5678-1234-567812345678"),
    )

    # Мок price_map
    mocker.patch.object(settings_bot.pricing, "price_map", {2: 100, 3: 150})

    router = SubscriptionRouter(
        bot=bot_mock,
        logger=fake_logger,
        subscription_service=subscription_service,
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
    # --- bot / message / query ---
    bot_mock = AsyncMock()

    msg_mock = AsyncMock()
    msg_mock.chat.id = 999
    msg_mock.message_id = 10

    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=999, username="admin")
    query_mock.answer = AsyncMock()

    # callback data (ВАЖНО: теперь есть transaction_id)
    callback_data = Mock(
        user_id=1,
        months=3,
        premium=True,
        transaction_id=UUID("12345678-1234-5678-1234-567812345678"),
    )

    # --- confirm_transaction result (DTO мок) ---
    user_schema = Mock(
        username="user",
        first_name="John",
        last_name="Doe",
        telegram_id=1,
        current_subscription=Mock(type="premium"),
    )

    confirm_transaction_mock = Mock(
        subscription_res=user_schema,
        referral_res=Mock(
            success=False,
            inviter_telegram_id=None,
        ),
    )

    # --- payment adapter ---
    payment_adapter_mock = AsyncMock()
    payment_adapter_mock.confirm_transaction.return_value = confirm_transaction_mock

    # --- subscription service ---
    subscription_service_mock = AsyncMock()
    subscription_service_mock.payment_adapter = payment_adapter_mock

    # --- referral service ---
    referral_service_mock = AsyncMock()

    # --- redis ---
    redis_mock = AsyncMock()

    # --- patch external funcs ---
    mocker.patch("bot.subscription.router.edit_admin_messages")
    mocker.patch("bot.subscription.router.send_to_admins")

    # --- router ---
    router = SubscriptionRouter(
        bot=bot_mock,
        logger=Mock(),
        subscription_service=subscription_service_mock,
        referral_service=referral_service_mock,
        redis_service=redis_mock,
    )

    # --- run ---
    await router.admin_confirm_payment(
        query=query_mock,
        state=AsyncMock(),
        callback_data=callback_data,
    )

    # --- asserts ---

    payment_adapter_mock.confirm_transaction.assert_awaited_once_with(
        callback_data.transaction_id
    )

    query_mock.answer.assert_awaited_once()

    bot_mock.send_message.assert_awaited()  # пользователь + возможно реферал

    referral_service_mock.grant_referral_bonus.assert_not_called()

    # state.clear внутри edit_admin_messages / try block
