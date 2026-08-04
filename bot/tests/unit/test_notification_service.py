from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramBadRequest

import bot.notification.services as notification_module
from bot.app_error.base_error import SubscriptionActivationFailedError
from bot.notification.services import NotificationService


def make_confirm(
    *,
    transaction_id=None,
    tg_id: int = 123,
    sub_type: str = "premium",
    months: int = 3,
    amount: int = 990,
    username: str = "borya",
    referral_success: bool = False,
    inviter_telegram_id: int | None = None,
):
    tx = SimpleNamespace(
        id=transaction_id or uuid4(),
        tg_id=tg_id,
        subscription_months=months,
        amount=amount,
    )
    subscription = SimpleNamespace(type=sub_type, end_date=None)
    user = SimpleNamespace(username=username, current_subscription=subscription)
    referral = SimpleNamespace(
        success=referral_success, inviter_telegram_id=inviter_telegram_id
    )
    return SimpleNamespace(
        transaction_res=tx, subscription_res=user, referral_res=referral
    )


@pytest.fixture(autouse=True)
def mock_send_to_admins(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(notification_module, "send_to_admins", mock)
    return mock


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Хранилище сообщений с оплатой — по умолчанию "ничего не найдено",
    поэтому большинство тестов идут по пути отправки нового сообщения.
    """
    storage = AsyncMock()
    storage.pop.return_value = None
    return storage


@pytest.mark.asyncio
async def test_notify_payment_confirmed_sends_styled_message_to_user_and_admin(
    mock_send_to_admins, mock_storage
):
    bot = AsyncMock()
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)
    confirm = make_confirm()

    await service.notify_payment_confirmed(confirm)

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 123
    assert "PREMIUM" in kwargs["text"]
    assert "3" in kwargs["text"]
    assert "990" in kwargs["text"]

    mock_send_to_admins.assert_awaited_once()
    admin_text = mock_send_to_admins.await_args.kwargs["message_text"]
    assert "123" in admin_text
    assert "borya" in admin_text


@pytest.mark.asyncio
async def test_notify_payment_confirmed_edits_tracked_message(
    mock_send_to_admins, mock_storage
):
    """Если для транзакции сохранено сообщение с кнопкой оплаты — редактируем
    именно его вместо отправки нового, чтобы не оставлять пользователю
    устаревшую ссылку.
    """
    mock_storage.pop.return_value = {"chat_id": 555, "message_id": 42}
    bot = AsyncMock()
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)
    confirm = make_confirm()

    await service.notify_payment_confirmed(confirm)

    bot.edit_message_text.assert_awaited_once()
    edit_kwargs = bot.edit_message_text.await_args.kwargs
    assert edit_kwargs["chat_id"] == 555
    assert edit_kwargs["message_id"] == 42
    assert edit_kwargs["reply_markup"] is None
    mock_storage.pop.assert_awaited_once_with(confirm.transaction_res.id)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_payment_confirmed_falls_back_to_send_when_edit_fails(
    mock_send_to_admins, mock_storage
):
    mock_storage.pop.return_value = {"chat_id": 555, "message_id": 42}
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock(
        side_effect=TelegramBadRequest(method="edit_message_text", message="too old")
    )
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)
    confirm = make_confirm()

    await service.notify_payment_confirmed(confirm)

    bot.send_message.assert_awaited_once()
    assert (
        bot.send_message.await_args.kwargs["chat_id"] == confirm.transaction_res.tg_id
    )


@pytest.mark.asyncio
async def test_notify_payment_confirmed_notifies_referral_inviter(
    mock_send_to_admins, mock_storage
):
    bot = AsyncMock()
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)
    confirm = make_confirm(referral_success=True, inviter_telegram_id=777)

    await service.notify_payment_confirmed(confirm)

    assert bot.send_message.await_count == 2
    inviter_call = bot.send_message.await_args_list[1]
    assert inviter_call.kwargs["chat_id"] == 777


@pytest.mark.asyncio
async def test_notify_payment_confirmed_raises_when_subscription_missing(
    mock_send_to_admins, mock_storage
):
    bot = AsyncMock()
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)
    confirm = make_confirm()
    confirm.subscription_res.current_subscription = None

    with pytest.raises(SubscriptionActivationFailedError):
        await service.notify_payment_confirmed(confirm)


@pytest.mark.asyncio
async def test_notify_payment_confirmed_alerts_admin_when_user_unreachable(
    mock_send_to_admins, mock_storage
):
    bot = AsyncMock()
    bot.send_message = AsyncMock(
        side_effect=TelegramBadRequest(method="send_message", message="ошибка")
    )
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)
    confirm = make_confirm()

    await service.notify_payment_confirmed(confirm)

    # Одно уведомление об ошибке доставки + одно обычное админ-уведомление.
    assert mock_send_to_admins.await_count == 2


@pytest.mark.asyncio
async def test_notify_payment_failed_notifies_user_only_on_plain_cancel(
    mock_send_to_admins, mock_storage
):
    bot = AsyncMock()
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)

    await service.notify_payment_failed(
        transaction_id=uuid4(), tg_id=123, is_chargeback=False
    )

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 123
    mock_send_to_admins.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_payment_failed_alerts_admin_on_chargeback(
    mock_send_to_admins, mock_storage
):
    bot = AsyncMock()
    service = NotificationService(bot=bot, payment_mess_storage=mock_storage)

    await service.notify_payment_failed(
        transaction_id=uuid4(), tg_id=123, is_chargeback=True
    )

    mock_send_to_admins.assert_awaited_once()
    admin_text = mock_send_to_admins.await_args.kwargs["message_text"]
    assert "ЧАРДЖБЭК" in admin_text
