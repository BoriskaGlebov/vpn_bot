from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.scheduler.services import SchedulerBotService, SubscriptionBotStats
from bot.scheduler.utils.scheduler_cron import expense_reminder, scheduled_check


@pytest.fixture
def fake_logger(monkeypatch):
    """Подменяем loguru logger на мок."""
    logger_mock = MagicMock()
    logger_mock.bind.return_value = logger_mock  # для chain calls
    monkeypatch.setattr("bot.scheduler.utils.scheduler_cron.logger", logger_mock)
    return logger_mock


@pytest.mark.asyncio
async def test_scheduled_check_logs_and_calls_service(fake_logger):
    # Мок-статистика
    stats_mock = SubscriptionBotStats(
        checked=10, expired=2, notified=5, configs_deleted=1
    )

    # Мок-сервис
    service_mock = AsyncMock(spec=SchedulerBotService)
    service_mock.check_all_subscriptions.return_value = stats_mock

    # Мокаем sleep
    with patch("asyncio.sleep", new=AsyncMock()):
        await scheduled_check(service_mock)

    service_mock.check_all_subscriptions.assert_awaited_once()

    # Проверяем, что success был вызван
    assert any(
        "Проверка подписок завершена" in str(args[0])
        for method_name, args, kwargs in fake_logger.method_calls
        if method_name == "success"
    )


# ---------------------------------------------------------------------------
# Тесты expense_reminder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_reminder_sends_to_admins():
    """expense_reminder вызывает send_to_admins с текстом и клавиатурой."""
    mock_bot = AsyncMock()

    with patch(
        "bot.scheduler.utils.scheduler_cron.send_to_admins", new_callable=AsyncMock
    ) as mock_send:
        await expense_reminder(bot_instance=mock_bot)

    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs.get("reply_markup") is not None
    assert call_kwargs.get("message_text")


@pytest.mark.asyncio
async def test_expense_reminder_correct_month():
    """Вызов 1 января — в тексте упоминается «декабрь» и предыдущий год."""
    from datetime import datetime

    mock_bot = AsyncMock()
    fake_now = datetime(2027, 1, 1, 10, 0, tzinfo=timezone.utc)

    with (
        patch(
            "bot.scheduler.utils.scheduler_cron.send_to_admins", new_callable=AsyncMock
        ) as mock_send,
        patch("bot.scheduler.utils.scheduler_cron.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = fake_now
        await expense_reminder(bot_instance=mock_bot)

    text = mock_send.call_args.kwargs.get("message_text", "")
    assert "декабрь" in text
    assert "2026" in text


@pytest.mark.asyncio
async def test_expense_reminder_handles_exception():
    """При ошибке expense_reminder не поднимает исключение, а логирует его."""
    mock_bot = AsyncMock()

    with (
        patch(
            "bot.scheduler.utils.scheduler_cron.send_to_admins",
            side_effect=RuntimeError("network error"),
        ),
        patch("bot.scheduler.utils.scheduler_cron.logger") as mock_logger,
    ):
        # Не должно поднять исключение
        await expense_reminder(bot_instance=mock_bot)

    mock_logger.exception.assert_called_once()
