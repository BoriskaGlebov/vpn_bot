from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def fake_bot():
    """Фикстура создает фейкового бота с мокнутым методом set_my_commands."""
    bot_mock = AsyncMock()
    return bot_mock


@pytest.fixture
def patch_bot(fake_bot):
    """
    Автоматически подменяет реального бота в модуле commands
    на фейкового.
    """
    with patch("bot.utils.commands.bot", fake_bot):
        yield fake_bot
