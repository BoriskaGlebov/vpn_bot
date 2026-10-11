"""Тесты api/core/database.py — пул соединений (#236) и decorator connection (#237)."""

import pytest
from sqlalchemy import StaticPool, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.core.config import settings_api
from api.core.database import connection, engine


def test_engine_pool_uses_configured_settings():
    """pool_size/max_overflow/pool_pre_ping/pool_recycle приходят из настроек,
    а не остаются захардкоженными дефолтами SQLAlchemy (pool_size=5,
    max_overflow=10, pool_pre_ping=False).
    """
    pool = engine.pool

    assert pool.size() == settings_api.db.pool_size
    assert pool._max_overflow == settings_api.db.max_overflow
    assert pool._pre_ping is settings_api.db.pool_pre_ping
    assert pool._recycle == settings_api.db.pool_recycle


def test_pool_pre_ping_enabled_by_default():
    """pool_pre_ping=True по умолчанию — иначе первые запросы после
    перезапуска/разрыва соединения на стороне Postgres падают с
    OperationalError на «мёртвом» соединении из пула.
    """
    assert settings_api.db.pool_pre_ping is True


@pytest.fixture
async def sqlite_session_factory(monkeypatch):
    """Подменяет async_session декоратора connection на SQLite-движок для теста."""
    sqlite_engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr("api.core.database.async_session", session_factory)
    yield session_factory
    await sqlite_engine.dispose()


@pytest.mark.asyncio
async def test_connection_decorator_commits_on_success(sqlite_session_factory):
    """Без переданного session декоратор сам открывает сессию и коммитит."""

    @connection()
    async def noop(session: AsyncSession) -> int:
        result = await session.execute(select(1))
        return result.scalar()

    assert await noop() == 1


@pytest.mark.asyncio
async def test_connection_decorator_applies_isolation_level(sqlite_session_factory):
    """isolation_level реально применяется к соединению, на котором исполняется
    декорированная функция (#237 — раньше либо падало, либо применялось не к
    той транзакции).
    """
    captured = {}

    @connection(isolation_level="SERIALIZABLE")
    async def capture_level(session: AsyncSession) -> None:
        conn = await session.connection()
        captured["level"] = await conn.get_isolation_level()

    await capture_level()

    assert captured["level"] == "SERIALIZABLE"


@pytest.mark.asyncio
async def test_connection_decorator_rolls_back_on_exception(sqlite_session_factory):
    """Исключение в декорированной функции приводит к rollback и re-raise."""

    @connection()
    async def boom(session: AsyncSession) -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await boom()


@pytest.mark.asyncio
async def test_connection_decorator_reuses_passed_session(sqlite_session_factory):
    """Если session передан явно (как в тестовых фикстурах), декоратор не
    открывает вторую — использует переданную как есть.
    """
    async with sqlite_session_factory() as existing_session:

        @connection()
        async def passthrough(session: AsyncSession) -> bool:
            return session is existing_session

        assert await passthrough(session=existing_session) is True
