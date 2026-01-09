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
from bot.redis_service import RedisAdminMessageStorage
from bot.utils import commands
from bot.utils.init_default_roles import init_default_roles_admins
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


@pytest.fixture
def fake_bot():
    bot = AsyncMock(spec=Bot)
    bot.get_me.return_value.first_name = "TestBot"
    bot.set_my_description.return_value = None
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def fake_logger(monkeypatch):
    logger = MagicMock(spec=real_logger)
    logger.bind.return_value = logger
    monkeypatch.setattr("bot.config.logger", logger)
    return logger


@pytest.fixture
def fake_redis(fake_logger):
    # Создаём экземпляр SettingsRedis, но подменяем методы асинхронными моками
    redis = SettingsRedis(redis_url="redis://fake_url", logger=fake_logger)
    redis._ensure_connection = AsyncMock(
        return_value=AsyncMock()
    )  # возвращаем мок соединения
    redis.set = AsyncMock(return_value=True)  # возвращает True для NX
    redis.get = AsyncMock(return_value=None)  # если нужен get
    redis.delete = AsyncMock(return_value=1)  # если нужен delete
    return redis


@pytest.fixture
def fake_redis_service(fake_redis, fake_logger):
    redis_service = RedisAdminMessageStorage(redis=fake_redis, logger=fake_logger)
    redis_service.get = AsyncMock(return_value=[])
    redis_service.add = AsyncMock()
    redis_service.clear = AsyncMock()
    return redis_service


@pytest.fixture
def patch_deps(fake_bot, fake_logger, monkeypatch):
    monkeypatch.setattr(commands, "bot", fake_bot)
    monkeypatch.setattr(commands, "logger", fake_logger)
    monkeypatch.setattr(settings_bot.messages, "description", "Описание работы Бота")
    monkeypatch.setattr(settings_bot, "admin_ids", {123, 456})
    return fake_bot, fake_logger


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
    return engine


@pytest.fixture(autouse=True)
async def setup_database(test_engine):
    from bot.referrals.models import Referral
    from bot.users.models import Role, Subscription, User, VPNConfig

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    os.remove("./test.db")


@pytest.fixture
async def session(test_engine):
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        await init_default_roles_admins(session=session)
        yield session


@pytest.fixture
def fake_state():
    fsm = AsyncMock(spec=FSMContext)
    fsm.get_data = AsyncMock(return_value={})
    fsm.clear = AsyncMock()
    fsm.set_state = AsyncMock()
    return fsm


@pytest.fixture
def make_fake_message():
    def _make(user_id: int = 123, text: str = "/start"):
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
        message.text = text
        message.message_id = 1000 + user_id
        message.answer = AsyncMock()
        message.answer_document = AsyncMock()
        message.edit_text = AsyncMock()
        message.delete = AsyncMock()
        return message

    return _make


@pytest.fixture
def make_fake_photo():
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
        message.message_id = 1000 + user_id
        # Для теста с фото
        message.photo = [type("Photo", (), {"file_id": "file123"})()]
        message.caption = "Caption text"
        message.text = None  # текст отсутствует, чтобы сработал блок для фото
        # Асинхронные методы
        message.answer = AsyncMock()
        message.answer_photo = AsyncMock()
        message.edit_text = AsyncMock()
        message.delete = AsyncMock()
        return message

    return _make


@pytest.fixture
def make_fake_query(make_fake_message):
    def _make(
        user_id: int = 999,
        data: str = "",
        username: str = "test_admin",
        first_name: str = "Admin",
    ):
        query = AsyncMock(spec=CallbackQuery)
        query.from_user = User(
            id=user_id,
            is_bot=False,
            first_name=first_name,
            username=username,
        )
        query.message = make_fake_message(user_id)
        query.id = f"query_{user_id}"
        query.data = data
        query.bot = AsyncMock()
        query.bot.send_message = AsyncMock()
        # Асинхронные методы
        query.answer = AsyncMock()
        query.message.edit_text = AsyncMock()  # чтобы гарантированно был async

        return query

    return _make


@pytest.fixture
def make_query_photo(make_fake_photo):
    """Фикстура для создания CallbackQuery с сообщением, содержащим фото."""

    def _make(
        user_id: int = 999,
        data: str = "",
        username: str = "test_admin",
        first_name: str = "Admin",
    ):
        query = AsyncMock(spec=CallbackQuery)
        query.from_user = User(
            id=user_id,
            is_bot=False,
            first_name=first_name,
            username=username,
        )

        # Используем make_fake_photo для создания сообщения с фото
        message = make_fake_photo(user_id)
        query.message = message

        query.id = f"query_{user_id}"
        query.data = data
        query.bot = AsyncMock()
        query.bot.send_message = AsyncMock()
        query.bot.send_photo = AsyncMock()  # нужен для confirm_news_handler

        # Асинхронные методы
        query.answer = AsyncMock()
        query.message.edit_text = AsyncMock()
        query.message.edit_caption = (
            AsyncMock()
        )  # чтобы можно было редактировать caption

        return query

    return _make


@pytest.fixture
def mock_asyncssh_connect():
    """Мок для asyncssh.connect"""
    with patch(
        "bot.vpn.utils.amnezia_wg.asyncssh.connect", new_callable=AsyncMock
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
        known_hosts=None,
        container="test-container",
    )


@pytest.fixture
def ssh_client_vpn():
    """Создаёт экземпляр клиента"""
    return AsyncSSHClientVPN(
        host="127.0.0.1",
        username="testuser",
        known_hosts=None,
        container="test-container",
    )
