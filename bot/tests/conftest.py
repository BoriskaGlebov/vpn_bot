import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, Message, User
from loguru import logger as real_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings_bot
from bot.database import Base
from bot.redis_manager import SettingsRedis
from bot.utils import commands
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


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
def fake_redis():
    # Создаём экземпляр SettingsRedis, но подменяем методы асинхронными моками
    redis = SettingsRedis(redis_url="redis://fake_url")

    # Подменяем методы на AsyncMock
    redis.get_admin_messages = AsyncMock(return_value=[])
    redis.clear_admin_messages = AsyncMock()
    redis.save_admin_message = AsyncMock()

    return redis


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
def fake_state():
    fsm = AsyncMock(spec=FSMContext)
    fsm.get_data = AsyncMock(return_value={})
    return fsm


@pytest.fixture
def make_fake_message():
    def _make(user_id: int = 123):
        user = User(
            id=user_id,
            is_bot=False,
            first_name=f"first_name_{user_id}",
            username=f"username_{user_id}",
        )
        chat = Chat(id=user_id, type="private")
        message = AsyncMock(spec=Message)
        message.from_user = user
        message.chat = chat
        message.text = "/start"
        message.message_id = 1000 + user_id
        message.answer = AsyncMock()
        message.edit_text = AsyncMock()
        message.delete = AsyncMock()
        return message

    return _make


@pytest.fixture
def make_fake_query(make_fake_message):
    def _make(user_id: int = 999):
        query = MagicMock(spec=CallbackQuery)
        query.from_user = User(
            id=user_id,
            is_bot=False,
            first_name="Admin",
            username="test_admin",
        )
        query.message = make_fake_message(user_id)
        query.id = f"query_{user_id}"

        # Асинхронные методы
        query.answer = AsyncMock()
        query.message.edit_text = AsyncMock()  # чтобы гарантированно был async

        return query

    return _make


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
