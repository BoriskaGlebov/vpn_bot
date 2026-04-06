from datetime import datetime, timezone
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, Message, User
from integrations.api_client import APIClient
from loguru import logger as real_logger
from users.schemas import SRoleOut, SSubscriptionOut, SUser, SUserOut

from bot.admin.adapter import AdminAPIAdapter
from bot.core.config import settings_bot
from bot.integrations.redis_client import RedisClient
from bot.news.adapter import NewsAPIAdapter
from bot.redis_service import RedisAdminMessageStorage
from bot.referrals.adapter import ReferralAPIAdapter
from bot.users.adapter import UsersAPIAdapter
from bot.utils import commands
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


@pytest.fixture
def fake_bot() -> AsyncMock:
    """Создаёт мок объекта бота aiogram.

    Настраивает минимально необходимое поведение:
    - `get_me` возвращает объект с `first_name`
    - `set_my_description` успешно выполняется
    - `send_message` является асинхронным методом

    Returns
        AsyncMock: Замоканный экземпляр Bot.

    """
    bot = AsyncMock(spec=Bot)

    bot.get_me.return_value.first_name = "TestBot"
    bot.set_my_description.return_value = None
    bot.send_message = AsyncMock()

    return bot


@pytest.fixture
def fake_logger(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Создаёт мок логгера и подменяет его в конфигурации.

    Используется для перехвата логирования в тестах, чтобы:
    - не было реального вывода
    - можно было проверять вызовы логгера

    Args:
        monkeypatch (pytest.MonkeyPatch): Инструмент pytest для подмены объектов.

    Returns
        MagicMock: Замоканный логгер.

    """
    logger = MagicMock(spec=real_logger)

    # loguru использует bind(), возвращаем тот же объект для цепочек вызовов
    logger.bind.return_value = logger

    # Подменяем логгер в конфиге приложения
    monkeypatch.setattr("bot.core.config.logger", logger)

    return logger


@pytest.fixture
def patch_deps(
    fake_bot: AsyncMock,
    fake_logger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> Tuple[AsyncMock, MagicMock]:
    """Подменяет зависимости в модуле commands.

    Заменяет:
    - bot → на fake_bot
    - logger → на fake_logger
    - description → тестовое значение
    - admin_ids → фиксированный набор

    Args:
        fake_bot (AsyncMock): Мок бота.
        fake_logger (MagicMock): Мок логгера.
        monkeypatch (pytest.MonkeyPatch): Инструмент подмены.

    Returns:
        Tuple[AsyncMock, MagicMock]: Используемые моки (bot, logger).
    """
    monkeypatch.setattr(commands, "bot", fake_bot)
    monkeypatch.setattr(commands, "logger", fake_logger)

    # Подменяем настройки
    monkeypatch.setattr(settings_bot.messages, "description", "Описание работы Бота")
    monkeypatch.setattr(settings_bot, "admin_ids", {123, 456})

    return fake_bot, fake_logger


@pytest.fixture
def fake_redis() -> RedisClient:
    """Создаёт мок Redis-клиента.

    Реальный клиент создаётся, но его методы заменяются на AsyncMock:
    - `_ensure_connection` → возвращает мок соединения
    - `set` → всегда True (например, для NX)
    - `get` → None (значение отсутствует)
    - `delete` → 1 (одна запись удалена)

    Returns:
        RedisClient: Замоканный Redis-клиент.
    """
    redis = RedisClient(redis_url="redis://fake_url")

    # Подменяем внутреннее соединение
    redis._ensure_connection = AsyncMock(return_value=AsyncMock())

    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)

    return redis


@pytest.fixture
def fake_redis_service(
    fake_redis: RedisClient,
) -> RedisAdminMessageStorage:
    """Создаёт мок сервиса хранения сообщений админов.

    Методы сервиса подменяются:
    - `get` → возвращает пустой список
    - `add` → AsyncMock без результата
    - `clear` → AsyncMock без результата

    Args:
        fake_redis (RedisClient): Мок Redis-клиента.
        fake_logger (MagicMock): Мок логгера (может использоваться внутри сервиса).

    Returns
        RedisAdminMessageStorage: Замоканный сервис.

    """
    redis_service = RedisAdminMessageStorage(redis=fake_redis)

    redis_service.get = AsyncMock(return_value=[])
    redis_service.add = AsyncMock()
    redis_service.clear = AsyncMock()

    return redis_service


@pytest.fixture
def mock_transport():
    """Фабрика для создания mock transport."""

    def _factory(handler):
        return httpx.MockTransport(handler)

    return _factory


@pytest.fixture
async def api_client():
    clients = []

    async def _create(handler):
        transport = httpx.MockTransport(handler)

        client = APIClient(
            base_url="test",
            port=8000,
        )

        client._client = httpx.AsyncClient(
            transport=transport,
            base_url=client.base_url,
        )

        clients.append(client)
        return client

    yield _create

    for client in clients:
        await client.close()


@pytest.fixture
def user_in():
    return SUser(
        telegram_id=123456,
        username="test_user",
        first_name="John",
        last_name="Doe",
    )


@pytest.fixture
def tg_user():
    class TgUser:
        def __init__(self):
            self.id = 123456
            self.username = "test_user"
            self.first_name = "John"
            self.last_name = "Doe"

    return TgUser()


@pytest.fixture
def role_out():
    return SRoleOut(
        id=1,
        name="user",
        description="Regular user",
    )


@pytest.fixture
def subscription_out():
    return SSubscriptionOut(
        id=1,
        type="trial",
        is_active=True,
        end_date=None,
        created_at=datetime.now(tz=timezone.utc),
    )


@pytest.fixture
def user_out(role_out, subscription_out):
    return SUserOut(
        id=1,
        telegram_id=123456,
        username="test_user",
        first_name="John",
        last_name="Doe",
        has_used_trial=False,
        role=role_out,
        subscriptions=[subscription_out],
        vpn_configs=[],
        current_subscription=subscription_out,
    )


@pytest.fixture
def user_response(user_out):
    return user_out.model_dump(mode="json")


@pytest.fixture
def fake_state():
    fsm = AsyncMock(spec=FSMContext)
    fsm.get_data = AsyncMock(return_value={})
    fsm.clear = AsyncMock()
    fsm.set_state = AsyncMock()
    return fsm


#
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
def news_adapter_mock() -> AsyncMock:
    mock_adapter = AsyncMock(spec=NewsAPIAdapter)
    mock_adapter.get_recipients.return_value = [1, 2, 3]
    return mock_adapter


@pytest.fixture
def mock_admin_adapter():
    """Фикстура для мокнутого AdminAPIAdapter"""
    adapter = AsyncMock(spec=AdminAPIAdapter)
    return adapter


@pytest.fixture
def mock_referral_adapter():
    """Фикстура с мокнутым адаптером."""
    adapter = AsyncMock(spec=ReferralAPIAdapter)
    return adapter


@pytest.fixture
def mock_users_adapter():
    adapter = AsyncMock(spec=UsersAPIAdapter)
    return adapter


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


#
#
# @pytest.fixture(scope="session")
# def test_engine():
#     engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
#     return engine
#
#
# @pytest.fixture(autouse=True)
# async def setup_database(test_engine):
#     async with test_engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)
#     yield
#     async with test_engine.begin() as conn:
#         await conn.run_sync(Base.metadata.drop_all)
#     await test_engine.dispose()
#     os.remove("./test.db")
#
#
# @pytest.fixture
# async def session(test_engine):
#     async_session = async_sessionmaker(
#         test_engine, class_=AsyncSession, expire_on_commit=False
#     )
#     async with async_session() as session:
#         await init_default_roles_admins(session=session)
#         yield session
#
#

#
