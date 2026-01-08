from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import SettingsBot
from bot.config import bot as real_bot
from bot.redis_manager import SettingsRedis
from bot.subscription.models import Subscription, SubscriptionType
from bot.users.dao import RoleDAO
from bot.users.models import Role, User
from bot.users.services import UserService


@pytest.fixture(scope="session")
def test_settings_bot() -> SettingsBot:
    """Фикстура для загрузки тестовых настроек из .env.test."""
    return SettingsBot(
        _env_file=Path(__file__).resolve().parent.parent.parent.parent / ".env.test"
    )


@pytest.fixture
def fake_redis() -> SettingsRedis:
    """Простейший мок для Redis."""
    return AsyncMock(spec=SettingsRedis)


@pytest.fixture
def user_service(fake_redis: SettingsRedis) -> UserService:
    """Инстанс UserService с тестовым Redis."""
    return UserService(redis=fake_redis)


@pytest.fixture(scope="session")
def test_admin_id(test_settings_bot: SettingsBot) -> int:
    """Фикстура для получения ID администратора из настроек."""
    return list(test_settings_bot.admin_ids)[0]


@pytest.fixture(scope="session")
async def test_bot(test_settings_bot: SettingsBot) -> AsyncGenerator[Bot, Any]:
    """Фикстура для интеграционных тестов с тестовым ботом."""
    bot_instance = Bot(
        token=test_settings_bot.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Патчим глобальный бот, чтобы код использовал именно тестовый экземпляр
    real_bot.__class__ = bot_instance.__class__
    real_bot.__dict__ = bot_instance.__dict__

    yield bot_instance

    await bot_instance.session.close()


@pytest.fixture
async def setup_roles(session: AsyncSession):
    """Создаёт роли в базе для тестов."""
    roles = await RoleDAO.find_all(session=session)
    yield roles
    for r in roles:
        await session.delete(r)


@pytest.fixture
async def setup_users(session: AsyncSession, setup_roles):
    """Создаёт пользователей с разными ролями и подписками."""
    admin_role, founder_role, user_role = setup_roles

    users = [
        User(
            id=1,
            first_name="Admin",
            last_name="One",
            username="admin1",
            telegram_id=111,
            role=admin_role,
            subscriptions=[
                Subscription(type=SubscriptionType.PREMIUM),
            ],
            vpn_configs=[],
        ),
        User(
            id=2,
            first_name="Founder",
            last_name="Two",
            username="founder1",
            telegram_id=222,
            role=founder_role,
            subscriptions=[
                Subscription(type=SubscriptionType.PREMIUM),
            ],
            vpn_configs=[],
        ),
        User(
            id=3,
            first_name="User",
            last_name="Three",
            username="user1",
            telegram_id=333,
            role=user_role,
            subscriptions=[
                Subscription(type=SubscriptionType.STANDARD),
            ],
            vpn_configs=[],
        ),
        User(
            id=4,
            first_name="User",
            last_name="User44",
            username="trial1",
            telegram_id=444,
            role=user_role,
            subscriptions=[
                Subscription(type=SubscriptionType.TRIAL),
            ],
            vpn_configs=[],
        ),
    ]
    session.add_all(users)
    await session.commit()
    yield users
    for u in users:
        await session.delete(u)
    await session.commit()
