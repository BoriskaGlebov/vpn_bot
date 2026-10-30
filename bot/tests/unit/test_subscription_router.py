from datetime import datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ReplyKeyboardRemove

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import (
    InvalidSubscriptionPeriodError,
    VPNConfigNotFoundError,
)
from bot.app_error.schema import ErrorDetail
from bot.promo.schemas import SPromoValidationResult
from bot.subscription.router import SubscriptionRouter, SubscriptionStates
from bot.subscription.schemas import SSubscriptionCheck
from bot.subscription.utils.sub_utils import get_correct_price_map
from bot.users.schemas import SVPNConfigOut
from shared.enums.admin_enum import RoleEnum
from shared.enums.promo_enum import PromoDiscountType


@pytest.mark.asyncio
async def test_show_subscription_options_premium_user(
    mocker,
    fake_bot,
    fake_state,
):
    bot_mock = fake_bot
    state_mock = fake_state
    user = mocker.Mock(id=123, username="testuser")

    service_mock = mocker.AsyncMock()
    service_mock.check_premium.return_value = SSubscriptionCheck(
        premium=True, role=RoleEnum.USER, is_active=True, used_trial=True
    )

    router = SubscriptionRouter(
        bot=bot_mock,
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router._show_subscription_options(chat_id=123, user=user, state=state_mock)

    service_mock.check_premium.assert_awaited_once_with(tg_id=123)
    bot_mock.send_message.assert_any_call(
        chat_id=123,
        text="Начнем оформление подписки",
        reply_markup=ReplyKeyboardRemove(),
    )
    state_mock.set_state.assert_awaited_once_with(SubscriptionStates.subscription_start)


@pytest.mark.asyncio
async def test_my_subscription_menu_shows_info_and_renew_button(
    mocker,
    fake_bot,
    make_fake_message,
    fake_state,
):
    message_mock = make_fake_message()

    service_mock = mocker.AsyncMock()
    service_mock.get_subscription_and_referral_info.return_value = "info text"
    service_mock.get_user_vpn_configs.return_value = [
        SVPNConfigOut(
            id=1,
            file_name="conf1.conf",
            pub_key="PUBKEY1",
            node_name="main",
            created_at=datetime(2026, 1, 1),
        ),
        SVPNConfigOut(
            id=2,
            file_name="conf2.conf",
            pub_key="PUBKEY2",
            node_name="sof",
            created_at=datetime(2026, 1, 2),
        ),
    ]

    router = SubscriptionRouter(
        bot=fake_bot,
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.my_subscription_menu(message=message_mock, state=fake_state)

    fake_state.clear.assert_awaited_once()
    service_mock.get_subscription_and_referral_info.assert_awaited_once_with(
        tg_id=message_mock.from_user.id
    )
    message_mock.answer.assert_awaited_once()
    _, kwargs = message_mock.answer.await_args
    assert kwargs["text"] == "info text"
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any(b.text == "🔄 Оформить / продлить подписку" for b in buttons)
    assert any("2026-01-01" in b.text and "#1" in b.text for b in buttons)
    assert any("2026-01-02" in b.text and "#2" in b.text for b in buttons)


@pytest.mark.asyncio
async def test_config_delete_confirm_shows_confirmation(mocker):
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=123, username="user")

    service_mock = mocker.AsyncMock()
    service_mock.get_user_vpn_configs.return_value = [
        SVPNConfigOut(
            id=1,
            file_name="conf1.conf",
            pub_key="PUBKEY1",
            created_at=datetime(2026, 1, 1),
        ),
    ]

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    callback_data = Mock(config_id=1)
    await router.config_delete_confirm(query=query_mock, callback_data=callback_data)

    query_mock.answer.assert_awaited()
    msg_mock.edit_text.assert_awaited_once()
    _, kwargs = msg_mock.edit_text.await_args
    assert "conf1.conf" in kwargs["text"]
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any(b.text == "✅ Да, удалить" for b in buttons)


@pytest.mark.asyncio
async def test_config_delete_confirm_not_found(mocker):
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=123, username="user")

    service_mock = mocker.AsyncMock()
    service_mock.get_user_vpn_configs.return_value = []

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    callback_data = Mock(config_id=999)
    with pytest.raises(VPNConfigNotFoundError):
        await router.config_delete_confirm(
            query=query_mock, callback_data=callback_data
        )


@pytest.mark.asyncio
async def test_config_delete_execute_deletes_and_refreshes(mocker):
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=123, username="user")

    config = SVPNConfigOut(
        id=1, file_name="conf1.conf", pub_key="PUBKEY1", created_at=datetime(2026, 1, 1)
    )
    service_mock = mocker.AsyncMock()
    service_mock.get_user_vpn_configs.return_value = [config]
    service_mock.get_subscription_and_referral_info.return_value = "info text"

    vpn_service_mock = mocker.AsyncMock()

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=vpn_service_mock,
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    callback_data = Mock(config_id=1)
    await router.config_delete_execute(query=query_mock, callback_data=callback_data)

    vpn_service_mock.delete_user_config.assert_awaited_once_with(
        tg_id=123, config=config
    )
    msg_mock.edit_text.assert_awaited_once()
    _, kwargs = msg_mock.edit_text.await_args
    assert "conf1.conf" in kwargs["text"]
    assert "info text" in kwargs["text"]


@pytest.mark.asyncio
async def test_config_delete_cancel_returns_to_menu(mocker):
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=123, username="user")

    service_mock = mocker.AsyncMock()
    service_mock.get_user_vpn_configs.return_value = []
    service_mock.get_subscription_and_referral_info.return_value = "info text"

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.config_delete_cancel(query=query_mock)

    query_mock.answer.assert_awaited()
    msg_mock.edit_text.assert_awaited_once()
    _, kwargs = msg_mock.edit_text.await_args
    assert kwargs["text"] == "info text"


@pytest.mark.asyncio
async def test_renew_subscription_selected_deletes_menu_and_shows_options(mocker):
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock

    service_mock = mocker.AsyncMock()
    service_mock.check_premium.return_value = SSubscriptionCheck(
        premium=False, role=RoleEnum.USER, is_active=False, used_trial=False
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=service_mock,
        referral_service=mocker.Mock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.renew_subscription_selected(query=query_mock, state=mocker.AsyncMock())

    query_mock.answer.assert_awaited()
    msg_mock.delete.assert_awaited_once()
    service_mock.check_premium.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_selected_paid(mocker):
    """Выбор платного периода создаёт транзакцию и показывает выбор способа оплаты."""
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock  # ключевой момент
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"premium": True}
    callback_data = Mock(months=3, founder=False)

    transaction_id = UUID("12345678-1234-5678-1234-567812345678")
    subscription_service_mock = mocker.AsyncMock()
    subscription_service_mock.create_transaction.return_value = Mock(
        id=transaction_id, payment_url="https://pay.platega.io/checkout/abc"
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=subscription_service_mock,
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.subscription_selected(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    query_mock.answer.assert_awaited()
    msg_mock.edit_text.assert_awaited()
    # ссылка на оплату и выбранный период сохраняются в state, а не в
    # callback_data кнопок — вместе с текущей (возможно дисконтированной
    # промокодом) ценой, нужной следующим экранам.
    _, update_kwargs = state_mock.update_data.call_args_list[-1]
    assert update_kwargs["payment_url"] == "https://pay.platega.io/checkout/abc"
    assert update_kwargs["months"] == 3
    assert update_kwargs["promo_code"] is None
    assert "current_price" in update_kwargs
    state_mock.set_state.assert_awaited_with(SubscriptionStates.select_payment_method)


@pytest.mark.asyncio
async def test_subscription_selected_ignores_forged_founder_flag(mocker):
    """#279: founder в данных кнопки подделан (True), но сервер в состоянии
    положил False — сумма и тип подписки считаются по состоянию, а не по
    callback-данным: founder-тариф дороже обычного, подмена не должна его
    давать по сниженной (обычной) цене или наоборот.
    """
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"premium": False, "founder": False}
    callback_data = Mock(months=1, founder=True)  # подделанный признак

    transaction_id = UUID("12345678-1234-5678-1234-567812345678")
    subscription_service_mock = mocker.AsyncMock()
    subscription_service_mock.create_transaction.return_value = Mock(
        id=transaction_id, payment_url=None
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=subscription_service_mock,
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.subscription_selected(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    # Стандартный тариф на 1 мес из app_config.local.toml (см. conftest) —
    # ключевая проверка в том, что is_founder=False ушёл в транзакцию,
    # а не True из подделанного callback_data.
    _, kwargs = subscription_service_mock.create_transaction.call_args
    assert kwargs["is_founder"] is False


@pytest.mark.asyncio
async def test_subscription_selected_unknown_months_raises_domain_error(mocker):
    """#278: months из callback-данных (от клиента) не найден в карте тарифов —
    доменная ошибка, а не необработанный KeyError.
    """
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"premium": False}
    callback_data = Mock(months=999, founder=False)

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=mocker.AsyncMock(),
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    with pytest.raises(InvalidSubscriptionPeriodError):
        await router.subscription_selected(
            query=query_mock, state=state_mock, callback_data=callback_data
        )


@pytest.mark.asyncio
async def test_subscription_selected_trial_already_used_notifies_admins(mocker):
    """Повторная попытка активировать триал показывает alert и уведомляет админов."""
    from bot.app_error.api_error import APIClientConflictError
    from bot.app_error.schema import ErrorDetail

    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=123, username="testuser")
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"premium": False}
    callback_data = Mock(founder=False)

    subscription_service_mock = mocker.AsyncMock()
    subscription_service_mock.start_trial_subscription.side_effect = (
        APIClientConflictError(
            status_code=409,
            error=ErrorDetail(
                code="trial_used", message="Пробный период уже использован"
            ),
        )
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=subscription_service_mock,
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )
    send_to_admins_mock = mocker.patch("bot.subscription.router.send_to_admins")

    await router.trial_selected(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    # answer() у callback можно вызвать только один раз — регрессия на баг,
    # когда из-за повторного answer() пользователь не видел alert с ошибкой.
    query_mock.answer.assert_called_once_with(
        "Пробный период уже использован", show_alert=True
    )
    send_to_admins_mock.assert_awaited_once()
    msg_mock.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_payment_method_selected_card(mocker):
    """Выбор оплаты картой показывает ссылку на оплату без кнопки "Я оплатил"."""
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {
        "premium": False,
        "payment_url": "https://pay.platega.io/checkout/abc",
    }
    transaction_id = UUID("12345678-1234-5678-1234-567812345678")
    callback_data = Mock(
        action="pay_card", months=3, founder=False, transaction_id=transaction_id
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=mocker.AsyncMock(),
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.payment_method_selected(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    msg_mock.edit_text.assert_awaited_once()
    _, kwargs = msg_mock.edit_text.await_args
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any(b.url == "https://pay.platega.io/checkout/abc" for b in buttons)
    assert not any(b.text == "✅ Я оплатил" for b in buttons)
    state_mock.set_state.assert_awaited_with(SubscriptionStates.confirm_payment)


@pytest.mark.asyncio
async def test_payment_method_selected_transfer(mocker):
    """Выбор оплаты переводом показывает кнопку "Я оплатил" без ссылки на оплату."""
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"premium": False}
    transaction_id = UUID("12345678-1234-5678-1234-567812345678")
    callback_data = Mock(
        action="pay_transfer", months=3, founder=False, transaction_id=transaction_id
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=mocker.AsyncMock(),
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.payment_method_selected(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    msg_mock.edit_text.assert_awaited_once()
    _, kwargs = msg_mock.edit_text.await_args
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert any(b.text == "✅ Я оплатил" for b in buttons)
    assert not any(b.url for b in buttons)
    state_mock.set_state.assert_awaited_with(SubscriptionStates.confirm_payment)


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
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
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
        transaction_res=Mock(amount=1000),
        referral_res=Mock(
            success=False,
            inviter_telegram_id=None,
        ),
    )

    # --- subscription service ---
    # Роутер зовёт self.subscription_service.confirm_transaction(...) напрямую
    # (обёртка над PaymentService/adapter уже внутри SubscriptionService).
    subscription_service_mock = AsyncMock()
    subscription_service_mock.confirm_transaction.return_value = (
        confirm_transaction_mock
    )

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
        vpn_service=AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    # --- run ---
    await router.admin_confirm_payment(
        query=query_mock,
        state=AsyncMock(),
        callback_data=callback_data,
    )

    # --- asserts ---

    subscription_service_mock.confirm_transaction.assert_awaited_once_with(
        callback_data.transaction_id
    )

    query_mock.answer.assert_awaited_once()

    bot_mock.send_message.assert_awaited()  # пользователь + возможно реферал

    referral_service_mock.grant_referral_bonus.assert_not_called()

    # state.clear внутри edit_admin_messages / try block


@pytest.mark.asyncio
async def test_admin_confirm_payment_user_blocked_bot_still_completes(mocker):
    """#276: пользователь заблокировал бота (TelegramForbiddenError) на
    отправке уведомления об оплате — это не должно прервать остальные шаги:
    бонус пригласившему, правку админских сообщений, state.clear().
    """
    bot_mock = AsyncMock()
    bot_mock.send_message.side_effect = TelegramForbiddenError(
        method=Mock(), message="Forbidden: bot was blocked by the user"
    )

    msg_mock = AsyncMock()
    msg_mock.chat.id = 999
    msg_mock.message_id = 10

    query_mock = AsyncMock()
    query_mock.message = msg_mock
    query_mock.from_user = Mock(id=999, username="admin")
    query_mock.answer = AsyncMock()

    callback_data = Mock(
        user_id=1,
        months=3,
        premium=True,
        transaction_id=UUID("12345678-1234-5678-1234-567812345678"),
    )

    user_schema = Mock(
        username="user",
        first_name="John",
        last_name="Doe",
        telegram_id=1,
        current_subscription=Mock(type="premium"),
    )

    confirm_transaction_mock = Mock(
        subscription_res=user_schema,
        transaction_res=Mock(amount=1000),
        referral_res=Mock(
            success=True,
            inviter_telegram_id=777,
            message="Реферал получил бонус",
        ),
    )

    subscription_service_mock = AsyncMock()
    subscription_service_mock.confirm_transaction.return_value = (
        confirm_transaction_mock
    )

    edit_admin_messages_mock = mocker.patch(
        "bot.subscription.router.edit_admin_messages", new=AsyncMock()
    )
    send_to_admins_mock = mocker.patch(
        "bot.subscription.router.send_to_admins", new=AsyncMock()
    )

    state_mock = AsyncMock()

    router = SubscriptionRouter(
        bot=bot_mock,
        logger=Mock(),
        subscription_service=subscription_service_mock,
        referral_service=AsyncMock(),
        redis_service=AsyncMock(),
        vpn_service=AsyncMock(),
        payment_mess_storage=AsyncMock(),
        promo_service=AsyncMock(),
    )

    await router.admin_confirm_payment(
        query=query_mock,
        state=state_mock,
        callback_data=callback_data,
    )

    # Уведомление пользователю упало, но админа предупредили об этом,
    # а не всё посыпалось UnboundLocalError-ом на referral_result.
    send_to_admins_mock.assert_awaited()
    # Остальные шаги подтверждения выполнены, несмотря на блокировку.
    edit_admin_messages_mock.assert_awaited_once()
    state_mock.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_subscription_mode_preserves_used_trial(mocker):
    """#280: used_trial терялся при переключении режима — trial=False
    жёстко возвращал кнопку триала тому, кто его уже использовал.
    """
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"founder": False, "used_trial": True}
    callback_data = Mock(mode="premium")

    kb_mock = mocker.patch("bot.subscription.router.subscription_options_kb")

    router = SubscriptionRouter(
        bot=AsyncMock(),
        logger=Mock(),
        subscription_service=AsyncMock(),
        referral_service=AsyncMock(),
        redis_service=AsyncMock(),
        vpn_service=AsyncMock(),
        payment_mess_storage=AsyncMock(),
        promo_service=AsyncMock(),
    )

    await router.toggle_subscription_mode(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    kb_mock.assert_called_once_with(premium=True, trial=True, founder=False)


@pytest.mark.asyncio
async def test_toggle_subscription_mode_preserves_founder(mocker):
    """#280: founder терялся при переключении режима — основатель видел
    обычные тарифы вместо своих после переключения standard/premium.
    """
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    state_mock.get_data.return_value = {"founder": True, "used_trial": False}
    callback_data = Mock(mode="standard")

    kb_mock = mocker.patch("bot.subscription.router.subscription_options_kb")

    router = SubscriptionRouter(
        bot=AsyncMock(),
        logger=Mock(),
        subscription_service=AsyncMock(),
        referral_service=AsyncMock(),
        redis_service=AsyncMock(),
        vpn_service=AsyncMock(),
        payment_mess_storage=AsyncMock(),
        promo_service=AsyncMock(),
    )

    await router.toggle_subscription_mode(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    # founder=True -> trial=True независимо от used_trial (та же логика,
    # что в cancel_subscription).
    kb_mock.assert_called_once_with(premium=False, trial=True, founder=True)


@pytest.mark.asyncio
async def test_enter_promo_code_prompt_shows_input_screen(mocker):
    """Нажатие "У меня промокод" переводит в состояние ввода кода."""
    msg_mock = AsyncMock()
    query_mock = AsyncMock()
    query_mock.message = msg_mock
    state_mock = AsyncMock()
    transaction_id = UUID("12345678-1234-5678-1234-567812345678")
    callback_data = Mock(months=3, founder=False, transaction_id=transaction_id)

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=mocker.AsyncMock(),
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=mocker.AsyncMock(),
    )

    await router.enter_promo_code_prompt(
        query=query_mock, state=state_mock, callback_data=callback_data
    )

    query_mock.answer.assert_awaited()
    msg_mock.edit_text.assert_awaited_once()
    state_mock.set_state.assert_awaited_once_with(SubscriptionStates.enter_promo_code)


@pytest.mark.asyncio
async def test_promo_code_entered_success_recreates_transaction(
    mocker, make_fake_message, fake_state
):
    """Валидный код пересчитывает цену и пересоздаёт транзакцию со скидкой."""
    message_mock = make_fake_message(text="SALE10")
    fake_state.get_data.return_value = {
        "months": 3,
        "premium": False,
        "founder": False,
    }

    base_price = get_correct_price_map(premium=False, founder=False)[3]
    discount_amount = base_price // 10
    final_amount = base_price - discount_amount
    validation = SPromoValidationResult(
        promo_code_id=1,
        code="SALE10",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        base_amount=base_price,
        discount_amount=discount_amount,
        final_amount=final_amount,
    )
    promo_service_mock = mocker.AsyncMock()
    promo_service_mock.validate_code.return_value = validation

    transaction_id = UUID("12345678-1234-5678-1234-567812345678")
    subscription_service_mock = mocker.AsyncMock()
    subscription_service_mock.create_transaction.return_value = Mock(
        id=transaction_id, payment_url="https://pay.platega.io/checkout/discounted"
    )

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=subscription_service_mock,
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=promo_service_mock,
    )

    await router.promo_code_entered(message=message_mock, state=fake_state)

    promo_service_mock.validate_code.assert_awaited_once_with(
        code="SALE10", base_amount=base_price
    )
    subscription_service_mock.create_transaction.assert_awaited_once_with(
        amount=base_price,
        subscription_months=3,
        is_premium=False,
        is_founder=False,
        promo_code="SALE10",
    )
    message_mock.answer.assert_awaited_once()
    _, kwargs = message_mock.answer.await_args
    assert "SALE10" in kwargs["text"]
    fake_state.update_data.assert_awaited_once_with(
        payment_url="https://pay.platega.io/checkout/discounted",
        current_price=final_amount,
        promo_code="SALE10",
    )
    fake_state.set_state.assert_awaited_once_with(
        SubscriptionStates.select_payment_method
    )


@pytest.mark.asyncio
async def test_promo_code_entered_invalid_code_shows_error_and_stays(
    mocker, make_fake_message, fake_state
):
    """Невалидный код не пересоздаёт транзакцию — пользователь видит причину
    отказа и может ввести другой код или отменить ввод.
    """
    message_mock = make_fake_message(text="EXPIRED")
    fake_state.get_data.return_value = {
        "months": 1,
        "premium": False,
        "founder": False,
    }

    promo_service_mock = mocker.AsyncMock()
    promo_service_mock.validate_code.side_effect = APIClientError(
        ErrorDetail(code="promo_code_inactive", message="Промокод истёк")
    )
    subscription_service_mock = mocker.AsyncMock()

    router = SubscriptionRouter(
        bot=mocker.AsyncMock(),
        logger=mocker.Mock(),
        subscription_service=subscription_service_mock,
        referral_service=mocker.AsyncMock(),
        redis_service=mocker.Mock(),
        vpn_service=mocker.AsyncMock(),
        payment_mess_storage=mocker.AsyncMock(),
        promo_service=promo_service_mock,
    )

    await router.promo_code_entered(message=message_mock, state=fake_state)

    subscription_service_mock.create_transaction.assert_not_called()
    message_mock.answer.assert_awaited_once()
    _, kwargs = message_mock.answer.await_args
    assert "Промокод истёк" in kwargs["text"]
    fake_state.set_state.assert_not_awaited()
