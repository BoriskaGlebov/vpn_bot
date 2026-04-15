import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from loguru import logger as real_logger
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.admin.dependencies import check_admin_role, get_admin_service
from api.admin.router import router
from api.core.database import Base
from api.core.dependencies import get_session
from api.main import app
from api.users.models import User
from api.users.utils.init_default_roles import init_default_roles_admins


@pytest.fixture
def fake_logger(monkeypatch):
    logger = MagicMock(spec=real_logger)
    logger.bind.return_value = logger
    monkeypatch.setattr("api.core.config.logger", logger)
    return logger


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine


@pytest.fixture(scope="session", autouse=True)
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def session(test_engine):
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        await init_default_roles_admins(session=session)

        yield session

        await session.rollback()


@pytest.fixture
def mock_admin():
    """Мок администратора."""
    admin = MagicMock(spec=User)
    admin.id = 1
    admin.telegram_id = 999999999
    return admin


# --- Dependency override ---


@pytest.fixture
def client(mock_service, session, mock_admin):
    with patch(
        "api.main.init_default_roles_admins",
        new=AsyncMock(),
    ):
        app.dependency_overrides[get_admin_service] = lambda: mock_service
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[check_admin_role] = lambda: mock_admin

        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture
def mock_execute_result():
    """
    Фикстура, имитирующая результат выполнения запроса SQLAlchemy.
    Позволяет переиспользовать объект в разных тестах.
    """
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


@pytest.fixture
def mock_session() -> AsyncMock:
    """Мок асинхронной сессии SQLAlchemy."""
    return AsyncMock(spec=AsyncSession)
