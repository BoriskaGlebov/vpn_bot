import re
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from starlette.requests import Request

from api.core.config import settings_api
from api.users.auth_admin import AdminAuth, hash_password, verify_password


def _make_login_request(username: str, password: str) -> Request:
    """Запрос starlette с форм-данными логина, без реального ASGI-сервера."""
    request = AsyncMock(spec=Request)
    request.form = AsyncMock(return_value={"username": username, "password": password})
    request.session = {}
    return request


class TestHashPassword:
    def test_verify_password_accepts_correct_password(self):
        encoded = hash_password("correct-password")

        assert verify_password("correct-password", encoded) is True

    def test_verify_password_rejects_wrong_password(self):
        encoded = hash_password("correct-password")

        assert verify_password("wrong-password", encoded) is False

    def test_verify_password_rejects_empty_hash(self):
        """ADMIN_PANEL_PASSWORD_HASH не задан — вход должен быть невозможен, а не падать."""
        assert verify_password("anything", "") is False

    def test_verify_password_rejects_malformed_hash(self):
        assert verify_password("anything", "not-a-valid-hash") is False

    def test_hash_password_uses_random_salt(self):
        """Два хеша одного пароля не совпадают — соль случайна."""
        assert hash_password("same-password") != hash_password("same-password")

    def test_hash_password_does_not_use_dollar_separator(self):
        """Разделитель полей — не "$" (регрессия на инцидент с деплоем).

        Значение проходит GitHub Secret -> bash heredoc -> Docker Compose
        env_file; Compose интерполирует "$VAR" внутри env_file-значений, из-за
        чего хеш с "$"-разделителем молча обрезался при попадании в контейнер.
        """
        encoded = hash_password("correct-password")

        assert "$" not in encoded
        assert encoded.count(".") == 3

    def test_hash_survives_compose_style_dollar_interpolation(self):
        """Хеш не содержит "$" — эмуляция интерполяции Docker Compose
        (замена "$ИМЯ_ПЕРЕМЕННОЙ" на пустую строку) не меняет значение,
        и verify_password по-прежнему проходит.
        """
        encoded = hash_password("correct-password")

        simulated_after_compose = re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", "", encoded)

        assert simulated_after_compose == encoded
        assert verify_password("correct-password", simulated_after_compose) is True


class TestAdminAuthLogin:
    @pytest.fixture(autouse=True)
    def _configure_credentials(self, monkeypatch):
        monkeypatch.setattr(settings_api, "admin_panel_user", "admin")
        monkeypatch.setattr(
            settings_api,
            "admin_panel_password_hash",
            SecretStr(hash_password("correct-password")),
        )

    @pytest.mark.asyncio
    async def test_login_succeeds_with_correct_credentials(self):
        request = _make_login_request("admin", "correct-password")

        result = await AdminAuth(secret_key="test").login(request)

        assert result is True
        assert request.session == {"admin": True}

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_password(self):
        request = _make_login_request("admin", "wrong-password")

        result = await AdminAuth(secret_key="test").login(request)

        assert result is False
        assert request.session == {}

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_username(self):
        request = _make_login_request("not-admin", "correct-password")

        result = await AdminAuth(secret_key="test").login(request)

        assert result is False

    @pytest.mark.asyncio
    async def test_login_rejects_db_password(self):
        """Регрессия: раньше логином/паролем служили учётные данные PostgreSQL."""
        request = _make_login_request(
            settings_api.db.user, settings_api.db.password.get_secret_value()
        )

        result = await AdminAuth(secret_key="test").login(request)

        assert result is False

    @pytest.mark.asyncio
    async def test_login_rejects_when_password_hash_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings_api, "admin_panel_password_hash", SecretStr(""))
        request = _make_login_request("admin", "correct-password")

        result = await AdminAuth(secret_key="test").login(request)

        assert result is False
