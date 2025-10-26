from unittest.mock import ANY, AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.config import settings_bot
from bot.subscription.router import SubscriptionStates


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_start_subscription(fake_message, fake_state, fake_bot):
    """Проверяет корректное начало процесса оформления подписки."""

    # Подготовка данных с корректной структурой
    settings_bot.MESSAGES = {
        "modes": {
            "subscription": {
                "start": (
                    "💎 Пробный период — 14 дней бесплатно!\n\n"
                    "После него вы можете выбрать один из вариантов подписки:\n"
                    "  • 1 месяц — 70₽\n"
                    "  • 3 месяца — 160₽\n"
                    "  • 6 месяцев — 300₽\n"
                    "  • 12 месяцев — 600₽\n\n"
                    "Выберите подходящий вариант 👇\n"  # <-- добавляем \n
                )
            }
        }
    }

    # Импортируем тестируемую функцию (чтобы избежать circular import)
    from bot.subscription.router import start_subscription

    # Мокаем клавиатуру (чтобы не зависеть от реализации)
    with patch(
        "bot.subscription.router.subscription_options_kb",
        return_value="mocked_keyboard",
    ):
        # Вызываем функцию
        await start_subscription(fake_message, fake_state)

    # Проверяем, что отправлено сообщение с правильным текстом и клавиатурой
    fake_message.answer.assert_awaited_once_with(
        text=settings_bot.MESSAGES["modes"]["subscription"]["start"],
        reply_markup="mocked_keyboard",
    )

    # Проверяем, что состояние установлено верно
    fake_state.set_state.assert_awaited_once_with(SubscriptionStates.subscription_start)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_subscription_selected_paid(fake_state, session):
    """Проверяет выбор платной подписки (price != 0)."""

    from bot.subscription.router import subscription_selected

    # Подготовка CallbackQuery
    fake_query = AsyncMock()
    fake_query.data = "sub_select:3"
    fake_query.from_user.id = 12345
    fake_query.message.chat.id = 12345
    fake_query.message.edit_text = AsyncMock()
    fake_query.answer = AsyncMock()

    # Мокаем payment_confirm_kb
    with patch(
        "bot.subscription.router.payment_confirm_kb",
        return_value="mocked_payment_keyboard",
    ):
        await subscription_selected(
            query=fake_query,
            state=fake_state,
        )

    fake_query.answer.assert_awaited_once_with("Выбрал 3 месяцев", show_alert=False)
    fake_query.message.edit_text.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(SubscriptionStates.select_period)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_subscription_selected_trial(fake_state, session):
    """Проверяет выбор бесплатного пробного периода (price == 0)."""

    from bot.subscription.router import subscription_selected

    # Подготовка CallbackQuery
    fake_query = AsyncMock()
    fake_query.data = "sub_select:14"
    fake_query.from_user.id = 12345
    fake_query.message.chat.id = 12345
    fake_query.message.delete = AsyncMock()
    fake_query.answer = AsyncMock()

    # Мокаем внешние зависимости
    with (
        patch("bot.subscription.router.bot.send_message", new=AsyncMock()) as mock_send,
        patch(
            "bot.subscription.router.SubscriptionDAO.activate_subscription",
            new=AsyncMock(),
        ),
    ):
        await subscription_selected(query=fake_query, state=fake_state)

    fake_query.message.delete.assert_awaited_once()
    mock_send.assert_awaited_once()  # сообщение пользователю
    fake_state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_user_paid(fake_state):
    """Проверяет поведение при подтверждении оплаты пользователем."""

    from bot.subscription.router import m_subscription, user_paid

    # Подготовка callback
    fake_query = AsyncMock()
    fake_query.data = "sub_paid:3"
    fake_query.from_user.id = 111
    fake_query.from_user.username = "tester"
    fake_query.message.chat.id = 111
    fake_query.message.edit_text = AsyncMock()
    fake_query.answer = AsyncMock()

    # Подмена текстов сообщений
    m_subscription["wait_for_paid"] = {
        "user": "Ожидаем подтверждение администратора...",
        "admin": "Админ, пользователь {username} оплатил {months} мес. за {price} руб.",
    }

    # Мокаем зависимости
    with (
        patch(
            "bot.subscription.router.admin_payment_kb", return_value="mocked_admin_kb"
        ),
        patch(
            "bot.subscription.router.send_to_admins", new=AsyncMock()
        ) as mock_send_admins,
    ):
        await user_paid(fake_query, fake_state)

    # Проверка вызова ответа пользователю
    fake_query.answer.assert_awaited_once()
    fake_query.message.edit_text.assert_awaited_once_with(
        "Ожидаем подтверждение администратора..."
    )

    # Проверка смены состояния FSM
    fake_state.set_state.assert_awaited_once_with(SubscriptionStates.wait_for_paid)

    # Проверяем, что уведомление ушло админам
    mock_send_admins.assert_awaited_once()
    args, kwargs = mock_send_admins.await_args
    assert kwargs["telegram_id"] == 111
    assert "оплатил" in kwargs["message_text"]


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_cancel_subscription_from_select_period(fake_state):
    """Проверяет отмену на этапе выбора периода (возврат к выбору)."""

    from bot.subscription.router import cancel_subscription

    # Подготовка CallbackQuery
    fake_query = AsyncMock()
    fake_query.message.chat.id = 1001
    fake_query.from_user.id = 1001
    fake_query.answer = AsyncMock()
    fake_query.message.edit_text = AsyncMock()

    # FSM возвращает текущее состояние "select_period"
    fake_state.get_state = AsyncMock(
        return_value=SubscriptionStates.select_period.state
    )

    with patch(
        "bot.subscription.router.subscription_options_kb",
        return_value="mocked_keyboard",
    ):
        await cancel_subscription(fake_query, fake_state)

    fake_query.answer.assert_awaited_once_with("Отменено ❌", show_alert=False)
    fake_query.message.edit_text.assert_awaited_once_with(
        text="Вы вернулись к выбору периода подписки ⏪",
        reply_markup="mocked_keyboard",
    )
    fake_state.set_state.assert_awaited_once_with(SubscriptionStates.subscription_start)


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_cancel_subscription_to_main_menu(fake_state):
    """Проверяет отмену с выходом в главное меню (без состояния или первое состояние)."""

    from bot.subscription.router import cancel_subscription

    fake_query = AsyncMock()
    fake_query.message.chat.id = 2002
    fake_query.from_user.id = 2002
    fake_query.answer = AsyncMock()
    fake_query.message.delete = AsyncMock()

    fake_state.get_state = AsyncMock(return_value=None)

    with (
        patch("bot.subscription.router.bot.send_message", new=AsyncMock()) as mock_send,
        patch("bot.subscription.router.main_kb", return_value="mocked_main_kb"),
    ):
        await cancel_subscription(fake_query, fake_state)

    fake_query.message.delete.assert_awaited_once()
    mock_send.assert_awaited_once_with(
        chat_id=2002,
        text="Вы отменили оформление подписки.",
        reply_markup="mocked_main_kb",
    )
    fake_state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_confirm_payment_success(session, fake_state):
    """Проверяет успешное подтверждение оплаты администратором."""

    from bot.subscription.router import admin_confirm_payment

    fake_query = AsyncMock()
    fake_query.data = "admin_confirm:999:3"
    fake_query.message.chat.id = 111
    fake_query.message.edit_text = AsyncMock()
    fake_query.answer = AsyncMock()
    fake_query.bot.send_message = AsyncMock()

    # Мокаем зависимости
    with (
        patch(
            "bot.subscription.router.SubscriptionDAO.activate_subscription",
            new=AsyncMock(),
        ) as mock_activate,
        patch(
            "bot.subscription.router.edit_admin_messages",
            new=AsyncMock(),
        ) as mock_edit,
    ):
        await admin_confirm_payment(query=fake_query, state=fake_state)

    # Проверяем, что callback подтверждён
    fake_query.answer.assert_awaited_once_with(
        "Админ подтвердил оплату", show_alert=False
    )

    # Проверяем, что вызван DAO для активации подписки
    mock_activate.assert_awaited_once()
    args, kwargs = mock_activate.await_args
    assert kwargs["stelegram_id"].telegram_id == 999
    assert kwargs["month"] == 3

    # Проверяем, что сообщение пользователю отправлено
    fake_query.bot.send_message.assert_awaited_once_with(
        chat_id=999,
        text="✅ Ваша подписка на 3 мес. успешно активирована! Спасибо ❤️",
        reply_markup=ANY,
    )

    # Проверяем, что были обновлены сообщения у админов
    mock_edit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_confirm_payment_user_message_fail(session, fake_state):
    """Проверяет ситуацию, когда сообщение пользователю не удалось отправить."""

    from bot.subscription.router import admin_confirm_payment

    fake_query = AsyncMock()
    fake_query.data = "admin_confirm:777:6"
    fake_query.message.chat.id = 111
    fake_query.answer = AsyncMock()
    fake_query.bot.send_message = AsyncMock(
        side_effect=TelegramBadRequest(
            method="sendMessage",
            message="can't send",
        )
    )
    fake_query.message.edit_text = AsyncMock()

    with (
        patch(
            "bot.subscription.router.SubscriptionDAO.activate_subscription",
            new=AsyncMock(),
        ),
        patch(
            "bot.subscription.router.send_to_admins",
            new=AsyncMock(),
        ) as mock_send_admins,
        patch(
            "bot.subscription.router.edit_admin_messages",
            new=AsyncMock(),
        ),
    ):
        await admin_confirm_payment(query=fake_query, state=fake_state)

    # Проверяем, что ошибка с пользователем обрабатывается и уведомлены админы
    mock_send_admins.assert_awaited_once()
    args, kwargs = mock_send_admins.await_args
    assert "Не удалось отправить" in kwargs["message_text"]


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_decline_payment_success(fake_state):
    """Проверяет успешное отклонение оплаты."""

    from bot.subscription.router import admin_decline_payment

    fake_query = AsyncMock()
    fake_query.data = "admin_decline:123:3"
    fake_query.message.chat.id = 111
    fake_query.from_user.id = 123
    fake_query.answer = AsyncMock()
    fake_query.bot.send_message = AsyncMock()

    with patch(
        "bot.subscription.router.edit_admin_messages", new=AsyncMock()
    ) as mock_edit:
        await admin_decline_payment(fake_query, fake_state)

    fake_query.answer.assert_awaited_once_with("Отклонено 🚫")
    fake_query.bot.send_message.assert_awaited_once_with(
        chat_id=123,
        text="❌ Оплата не подтверждена. Если вы уверены, что оплата была, свяжитесь с поддержкой.",
        reply_markup=ANY,  # или из unittest.mock import ANY
    )
    mock_edit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_admin_decline_payment_user_message_fail(fake_state):
    """Проверяет отклонение, когда сообщение пользователю не отправилось."""

    from bot.subscription.router import admin_decline_payment

    fake_query = AsyncMock()
    fake_query.data = "admin_decline:456:6"
    fake_query.message.chat.id = 111
    fake_query.from_user.id = 456
    fake_query.answer = AsyncMock()
    fake_query.bot.send_message = AsyncMock(
        side_effect=TelegramBadRequest(method="sendMessage", message="can't send")
    )

    with patch(
        "bot.subscription.router.edit_admin_messages", new=AsyncMock()
    ) as mock_edit:
        await admin_decline_payment(fake_query, fake_state)

    fake_query.answer.assert_awaited_once_with("Отклонено 🚫")
    fake_query.bot.send_message.assert_awaited_once()
    mock_edit.assert_awaited_once()
