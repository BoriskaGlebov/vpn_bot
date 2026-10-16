"""Тесты api/core/config.py — секреты без значений по умолчанию (#247)."""

import pytest
from pydantic import ValidationError

from api.core.config import SettingsAPI

_VALID_DB = {"user": "u", "password": "p", "database": "d"}


def test_missing_session_secret_fails_fast(monkeypatch):
    """Без SESSION_SECRET приложение не должно подниматься с дефолтом."""
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    with pytest.raises(ValidationError, match="session_secret"):
        SettingsAPI(
            _env_file=None,
            db=_VALID_DB,
            internal_api_secret="x",
        )


def test_missing_internal_api_secret_fails_fast(monkeypatch):
    """Без INTERNAL_API_SECRET приложение не должно подниматься с дефолтом."""
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)

    with pytest.raises(ValidationError, match="internal_api_secret"):
        SettingsAPI(
            _env_file=None,
            db=_VALID_DB,
            session_secret="x",
        )


def test_settings_api_loads_with_explicit_secrets():
    """С обоими секретами, переданными явно, настройки собираются без ошибок."""
    settings = SettingsAPI(
        _env_file=None,
        db=_VALID_DB,
        session_secret="explicit-session-secret",
        internal_api_secret="explicit-internal-secret",
    )

    assert settings.session_secret.get_secret_value() == "explicit-session-secret"
    assert settings.internal_api_secret.get_secret_value() == "explicit-internal-secret"
