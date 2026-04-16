from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.scheduler.services import SchedulerBotService, SubscriptionBotStats
from bot.scheduler.utils.scheduler_cron import scheduled_check


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
