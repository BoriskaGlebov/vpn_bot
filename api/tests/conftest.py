import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from loguru import logger as real_logger
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.admin.dependencies import check_admin_role, get_admin_service
from api.core.database import Base
from api.core.dependencies import get_session
from api.main import app
from api.payment.dependencies import get_payment_service
from api.payment.schemas import SYearIncome
from api.users.models import User
from api.users.utils.init_default_roles import init_default_roles_admins
from shared.enums.admin_enum import RoleEnum


def fake_user(role: str = RoleEnum.USER.value) -> SimpleNamespace:
    """Лёгкая замена get_current_user для роутер-тестов (без похода в БД)."""
    return SimpleNamespace(
        id=1,
        telegram_id=123,
        username="test",
        has_used_trial=False,
        role=SimpleNamespace(name=role),
    )


def fake_admin() -> SimpleNamespace:
    """Лёгкая замена check_admin_role для роутер-тестов (без похода в БД)."""
    return SimpleNamespace(
        id=1,
        telegram_id=123,
        role=SimpleNamespace(name=RoleEnum.ADMIN.value),
    )


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


class FakePaymentService:
    async def get_year_income(self, session, year):
        return SYearIncome(year_income=1500)


@pytest.fixture
def mock_payment_service():
    return FakePaymentService()


# --- Dependency override ---


@pytest.fixture
def client(mock_service, session, mock_admin, mock_payment_service):
    with patch(
        "api.main.init_default_roles_admins",
        new=AsyncMock(),
    ):
        app.dependency_overrides[get_admin_service] = lambda: mock_service
        app.dependency_overrides[get_payment_service] = lambda: mock_payment_service
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


@pytest.fixture
def make_client():
    """Фабрика TestClient с настраиваемыми dependency_overrides.

    Убирает дублирование boilerplate (patch init_default_roles_admins +
    dependency_overrides + очистка) из client-фикстур каждого роутер-теста.
    Использование:

        @pytest.fixture
        def client(make_client, mock_service, mock_session):
            with make_client({
                get_news_service: lambda: mock_service,
                get_session: lambda: mock_session,
            }) as c:
                yield c
    """

    @contextmanager
    def _make_client(overrides: dict):
        with patch(
            "api.main.init_default_roles_admins",
            new=AsyncMock(),
        ):
            app.dependency_overrides.update(overrides)
            try:
                with TestClient(app) as c:
                    yield c
            finally:
                app.dependency_overrides.clear()

    return _make_client
