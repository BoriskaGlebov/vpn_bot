from unittest.mock import ANY, AsyncMock, patch

import pytest

from bot.config import settings_bot
from bot.redis_manager import SettingsRedis
from bot.subscription.keyboards.inline_kb import (
    AdminPaymentCB,
    SubscriptionCB,
    ToggleSubscriptionCB,
)
from bot.subscription.router import (
    SubscriptionRouter,
    SubscriptionStates,
    m_subscription,
)
from bot.subscription.services import SubscriptionService
from bot.users.keyboards.markup_kb import main_kb


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_start_subscription_user_defined(
    fake_bot, fake_logger, make_fake_message, fake_state
):
    message = make_fake_message(user_id=1)
    state = fake_state

    # Создаем мок сервиса подписки
    subscription_service = AsyncMock(spec=SubscriptionService)
    subscription_service.check_premium.return_value = (False, "user", False)

    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.start_subscription(message=message, state=state)

    # Проверка вызова check_premium
    subscription_service.check_premium.assert_awaited_once_with(session=ANY, tg_id=1)

    # Проверка вызова message.answer с нужным текстом и клавиатурой
    assert message.answer.await_count == 1
    called_args, called_kwargs = message.answer.await_args
    assert "💎 Пробный период — 7 дней бесплатно!" in called_kwargs["text"]
    assert called_kwargs["reply_markup"] is not None

    # Проверка установки состояния и обновления данных
    state.set_state.assert_awaited_once_with(SubscriptionStates.subscription_start)
    state.update_data.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_start_subscription_user_none(
    patch_deps, make_fake_message, fake_state, fake_bot, fake_logger
):
    message = make_fake_message(user_id=1)
    message.from_user = None  # пользователь не определен
    state = fake_state

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.start_subscription(message=message, state=state)

    # Проверка, что логгер вызван для ошибки
    fake_logger.error.assert_called_once_with("user undefined")

    # Проверка, что методы state и service не вызывались
    state.set_state.assert_not_called()
    subscription_service.check_premium.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_subscription_selected_paid(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # Создаем CallbackQuery с months > 0
    callback_data = SubscriptionCB(action="paid", months=1)
    query = make_fake_query(user_id=1, data="", username="test_user")
    state = fake_state
    state.get_data = AsyncMock(return_value={"premium": False})

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.subscription_selected(
        query=query, state=state, callback_data=callback_data
    )

    # Проверка, что query.answer вызван
    query.answer.assert_awaited_once_with("Выбрал 1 месяцев", show_alert=False)

    # Проверка, что msg.edit_text вызван с правильным текстом
    query.message.edit_text.assert_awaited_once()
    args, kwargs = query.message.edit_text.await_args
    assert "1" in kwargs["text"]
    assert "STANDARD" in kwargs["text"]
    assert kwargs["reply_markup"] is not None

    # Проверка, что состояние FSM обновлено
    state.set_state.assert_awaited_once_with(SubscriptionStates.select_period)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_subscription_selected_trial(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # Создаем CallbackQuery с months = 0 (триал)
    callback_data = SubscriptionCB(action="paid", months=7)
    query = make_fake_query(user_id=1, data="", username="test_user")
    state = fake_state
    state.get_data.return_value = AsyncMock(return_value={})

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.subscription_selected(
        query=query, state=state, callback_data=callback_data
    )

    # Проверка вызовов для триала
    subscription_service.start_trial_subscription.assert_awaited_once_with(
        session=ANY, user_id=1, days=callback_data.months
    )
    query.answer.assert_awaited_once_with("Выбрал пробный период", show_alert=False)
    query.message.delete.assert_awaited_once()
    fake_bot.send_message.assert_awaited_once()
    state.clear.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_subscription_selected_user_none(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    callback_data = SubscriptionCB(action="paid", months=1)
    query = make_fake_query(user_id=1)
    query.from_user = None
    state = fake_state

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.subscription_selected(
        query=query, state=state, callback_data=callback_data
    )

    # Проверка логирования ошибки
    fake_logger.error.assert_called_once_with("user undefined")


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_toggle_subscription_mode_premium(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # Пользователь выбирает премиум режим
    callback_data = ToggleSubscriptionCB(mode="premium")
    query = make_fake_query(user_id=1)
    state = fake_state

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.toggle_subscription_mode(
        query=query, state=state, callback_data=callback_data
    )

    # Проверка, что текст редактирован
    query.message.edit_text.assert_awaited_once()
    args, kwargs = query.message.edit_text.await_args
    assert str(settings_bot.MAX_CONFIGS_PER_USER * 2) in kwargs["text"]
    assert kwargs["reply_markup"] is not None

    # Проверка, что query.answer вызван
    query.answer.assert_awaited_once_with("")

    # Проверка, что state.update_data вызван с premium=True
    state.update_data.assert_awaited_once_with(premium=True)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_toggle_subscription_mode_standard(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # Пользователь выбирает стандартный режим
    callback_data = ToggleSubscriptionCB(mode="standard")
    query = make_fake_query(user_id=1)
    state = fake_state

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.toggle_subscription_mode(
        query=query, state=state, callback_data=callback_data
    )

    # Проверка, что текст редактирован
    query.message.edit_text.assert_awaited_once()
    args, kwargs = query.message.edit_text.await_args
    assert kwargs["reply_markup"] is not None

    # Проверка, что query.answer вызван
    query.answer.assert_awaited_once_with("")

    # Проверка, что state.update_data вызван с premium=False
    state.update_data.assert_awaited_once_with(premium=False)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_toggle_subscription_mode_msg_none(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # Сообщение недоступно
    callback_data = ToggleSubscriptionCB(mode="premium")
    query = make_fake_query(user_id=1)
    query.message = None  # недоступно
    state = fake_state

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.toggle_subscription_mode(
        query=query, state=state, callback_data=callback_data
    )

    # Проверка, что методы не вызваны
    state.update_data.assert_not_called()
    query.answer.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_user_paid_standard(fake_bot, fake_logger, fake_state, make_fake_query):
    callback_data = SubscriptionCB(action="paid", months=1)
    query = make_fake_query(user_id=1, username="test_user")
    state = fake_state
    state.get_data = AsyncMock(return_value={"premium": False})

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    # Патчим redis_manager внутри send_to_admins
    with patch(
        "bot.redis_manager.redis_manager.save_admin_message", new_callable=AsyncMock
    ) as mock_save:
        await router.user_paid(query=query, state=state, callback_data=callback_data)

    # Проверка установки состояния FSM
    state.set_state.assert_awaited_once_with(SubscriptionStates.wait_for_paid)

    # Проверка вызова query.answer
    query.answer.assert_awaited_once_with("Пользователь нажал оплату (1 мес, 70₽)")

    # Проверка редактирования сообщения
    query.message.edit_text.assert_awaited_once_with(
        m_subscription["wait_for_paid"]["user"]
    )

    # Проверка, что save_admin_message был вызван
    mock_save.await_count == 2


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_user_paid_premium(fake_bot, fake_logger, fake_state, make_fake_query):
    # Создаем CallbackQuery для премиум режима
    callback_data = SubscriptionCB(action="paid", months=1)
    query = make_fake_query(user_id=2, username="premium_user")
    state = fake_state
    state.get_data = AsyncMock(return_value={"premium": True})

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    # Патчим redis_manager.save_admin_message, чтобы не сериализовать AsyncMock
    with patch(
        "bot.redis_manager.redis_manager.save_admin_message", new_callable=AsyncMock
    ) as mock_save:
        # Вызов метода
        await router.user_paid(query=query, state=state, callback_data=callback_data)

    # Цена удваивается для премиум
    query.answer.assert_awaited_once_with("Пользователь нажал оплату (1 мес, 140₽)")

    # Проверка редактирования сообщения
    query.message.edit_text.assert_awaited_once_with(
        m_subscription["wait_for_paid"]["user"]
    )

    # Проверка установки состояния FSM
    state.set_state.assert_awaited_once_with(SubscriptionStates.wait_for_paid)

    # Проверка вызова save_admin_message
    mock_save.await_count = 2
    # Получаем аргументы последнего вызова
    last_call_args, last_call_kwargs = mock_save.await_args_list[-1]
    assert last_call_kwargs["user_id"] == 2


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_cancel_subscription_select_period(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    query = make_fake_query(user_id=1, username="test_user")
    state = fake_state
    state.get_state = AsyncMock(return_value=SubscriptionStates.select_period.state)
    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.cancel_subscription(query=query, state=state)

    query.answer.assert_awaited_once_with("Отменено ❌", show_alert=False)
    query.message.edit_text.assert_awaited_once()
    state.set_state.assert_awaited_once_with(SubscriptionStates.subscription_start)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_cancel_subscription_first_step(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    query = make_fake_query(user_id=1, username="test_user")
    state = fake_state
    state.get_state = AsyncMock(return_value=None)
    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    await router.cancel_subscription(query=query, state=state)

    query.answer.assert_awaited_once_with("Отменено ❌", show_alert=False)
    query.message.delete.assert_awaited_once()
    fake_bot.send_message.assert_awaited_once_with(
        chat_id=1,
        text="Вы отменили оформление подписки.",
    )
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_confirm_payment_success(
    fake_bot, fake_logger, fake_state, make_fake_query, monkeypatch
):
    # Создаём CallbackQuery
    callback_data = AdminPaymentCB(user_id=1, months=1, premium=True, action="confirm")
    query = make_fake_query(user_id=999, username="admin_user")

    # Мок состояния
    state = fake_state

    # Мок сервиса подписки
    user_schema_mock = AsyncMock()
    user_schema_mock.username = "test_user"
    user_schema_mock.subscription.type = "premium"

    subscription_service = AsyncMock(spec=SubscriptionService)
    subscription_service.activate_paid_subscription.return_value = user_schema_mock

    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )
    # Мок зависимостей
    monkeypatch.setattr(
        "bot.subscription.router.send_to_admins", AsyncMock(return_value=[])
    )
    monkeypatch.setattr("bot.subscription.router.edit_admin_messages", AsyncMock())
    monkeypatch.setattr(
        "bot.subscription.router.redis_manager", AsyncMock(spec=SettingsRedis)
    )
    # Вызов метода
    await router.admin_confirm_payment(
        query=query, state=state, callback_data=callback_data
    )

    # Проверки
    query.answer.assert_awaited_once_with("Админ подтвердил оплату", show_alert=False)
    subscription_service.activate_paid_subscription.assert_awaited_once_with(
        ANY, 1, 1, True
    )
    query.bot.send_message.assert_awaited_once()
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_decline_payment_success(
    fake_bot, fake_logger, fake_state, make_fake_query, monkeypatch
):
    # Создаем CallbackQuery и callback_data
    callback_data = AdminPaymentCB(user_id=1, months=1, premium=True, action="decline")
    query = make_fake_query(user_id=999, username="admin_user")
    query.bot = fake_bot  # добавляем бот

    # Подменяем edit_admin_messages и send_message
    mock_edit_admin_messages = AsyncMock()
    monkeypatch.setattr(
        "bot.subscription.router.edit_admin_messages", mock_edit_admin_messages
    )

    subscription_service = AsyncMock(spec=SubscriptionService)
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    # Вызов метода
    await router.admin_decline_payment(
        query=query, state=fake_state, callback_data=callback_data
    )

    # Проверка, что ответ пользователю вызван
    query.answer.assert_awaited_once_with("Отклонено 🚫")

    # Проверка отправки сообщения пользователю
    query.bot.send_message.assert_awaited_once_with(
        chat_id=1,
        text=m_subscription.get("decline_paid", {}).get("user", ""),
        reply_markup=main_kb(active_subscription=False),
    )

    # Проверка вызова edit_admin_messages
    mock_edit_admin_messages.assert_awaited_once()
    called_args, called_kwargs = mock_edit_admin_messages.await_args
    assert f"{callback_data.user_id}" in str(called_kwargs.get("new_text", ""))


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_decline_payment_no_message(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # query.message = None
    callback_data = AdminPaymentCB(user_id=1, months=1, premium=True, action="decline")
    query = make_fake_query(user_id=999, username="admin_user")
    query.message = None
    query.bot = fake_bot

    subscription_service = AsyncMock()
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    result = await router.admin_decline_payment(
        query=query, state=fake_state, callback_data=callback_data
    )
    assert result is None


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_decline_payment_no_bot(
    fake_bot, fake_logger, fake_state, make_fake_query
):
    # query.bot = None
    callback_data = AdminPaymentCB(user_id=1, months=1, premium=True, action="decline")
    query = make_fake_query(user_id=999, username="admin_user")
    query.bot = None

    subscription_service = AsyncMock()
    router = SubscriptionRouter(
        bot=fake_bot, logger=fake_logger, subscription_service=subscription_service
    )

    result = await router.admin_decline_payment(
        query=query, state=fake_state, callback_data=callback_data
    )
    assert result is None
