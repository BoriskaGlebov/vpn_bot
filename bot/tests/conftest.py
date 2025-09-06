from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.middleware import exception_middleware
from bot.utils import commands


@pytest.fixture
def fake_bot():
    bot = AsyncMock()
    return bot


@pytest.fixture
def fake_logger():
    logger = MagicMock()
    # чтобы logger.bind(...) не ломало цепочку, пусть возвращает себя же
    logger.bind.return_value = logger
    return logger


@pytest.fixture
def patch_deps(fake_bot, fake_logger, monkeypatch):
    """
    Подменяет в bot.commands бот и логгер на фейковые объекты.
    Через monkeypatch — pytest сам откатит изменения после теста.
    """
    monkeypatch.setattr(commands, "bot", fake_bot)
    monkeypatch.setattr(commands, "logger", fake_logger)

    # Мокаем middleware, чтобы он не ловил исключения
    monkeypatch.setattr(
        exception_middleware, "ErrorHandlerMiddleware", lambda *a, **kw: None
    )
    return fake_bot, fake_logger
