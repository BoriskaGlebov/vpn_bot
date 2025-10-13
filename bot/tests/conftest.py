from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from loguru import logger as real_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings_bot
from bot.database import Base
from bot.utils import commands


@pytest.fixture
def fake_bot():
    bot = AsyncMock(spec=Bot)
    bot.get_me.return_value.first_name = "TestBot"
    bot.set_my_description.return_value = None
    return bot


@pytest.fixture
def fake_logger(monkeypatch):
    logger = MagicMock(spec=real_logger)
    logger.bind.return_value = logger
    monkeypatch.setattr("bot.config.logger", logger)
    return logger


@pytest.fixture
def patch_deps(fake_bot, fake_logger, monkeypatch):
    monkeypatch.setattr(commands, "bot", fake_bot)
    monkeypatch.setattr(commands, "logger", fake_logger)
    monkeypatch.setattr(settings_bot, "MESSAGES", {"description": "описание"})
    monkeypatch.setattr(settings_bot, "ADMIN_IDS", [123, 456])
    return fake_bot, fake_logger


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
    return engine


@pytest.fixture(scope="session", autouse=True)
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # после тестов можно удалить файл
    await test_engine.dispose()
    os.remove("./test.db")


@pytest.fixture()
async def session(test_engine):
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:

        yield session


@pytest.fixture
def mock_asyncssh_connect():
    """Мок для asyncssh.connect"""
    with patch(
        "bot.vpn_router.utils.amnezia_wg.asyncssh.connect", new_callable=AsyncMock
    ) as mock_connect:
        mock_conn = AsyncMock()
        mock_process = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.create_process.return_value = mock_process
        yield mock_connect, mock_conn, mock_process


@pytest.fixture
def ssh_client():
    """Создаёт экземпляр клиента"""
    return AsyncSSHClientWG(
        host="127.0.0.1",
        username="testuser",
        key_filename=None,
        known_hosts=None,
        container="test-container",
    )


@pytest.fixture
def ssh_client_vpn():
    """Создаёт экземпляр клиента"""
    return AsyncSSHClientVPN(
        host="127.0.0.1",
        username="testuser",
        key_filename=None,
        known_hosts=None,
        container="test-container",
    )
