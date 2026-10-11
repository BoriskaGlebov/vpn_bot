"""Тесты api/core/database.py — настройки пула соединений (#236)."""

from api.core.config import settings_api
from api.core.database import engine


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
