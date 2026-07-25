from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.middleware.base import BaseHTTPMiddleware

from api.core.config import settings_api
from api.middleware.auth_middleware import AuthMiddleware


class _FakeDBSessionMiddleware(BaseHTTPMiddleware):
    """Имитирует DBSessionMiddleware, устанавливая request.state.db."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.db = None
        return await call_next(request)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        settings_api, "internal_api_secret", SecretStr("test-internal-secret")
    )

    application = FastAPI()
    application.add_middleware(AuthMiddleware)
    application.add_middleware(_FakeDBSessionMiddleware)

    @application.get("/whoami")
    async def whoami(request: Request) -> dict:
        user = getattr(request.state, "user", "unset")
        return {"user_id": getattr(user, "id", None) if user else user}

    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_missing_internal_secret_ignores_telegram_id(client):
    """Без X-Internal-Secret заголовок X-Telegram-Id не должен приниматься во внимание."""
    response = await client.get("/whoami", headers={"X-Telegram-Id": "123"})

    assert response.json() == {"user_id": None}


@pytest.mark.asyncio
async def test_wrong_internal_secret_ignores_telegram_id(client):
    """Неверный секрет должен вести себя так же, как его отсутствие."""
    response = await client.get(
        "/whoami",
        headers={"X-Telegram-Id": "123", "X-Internal-Secret": "wrong-secret"},
    )

    assert response.json() == {"user_id": None}


@pytest.mark.asyncio
async def test_correct_internal_secret_resolves_user(client, monkeypatch):
    """С верным секретом X-Telegram-Id обрабатывается как раньше."""
    fake_user = AsyncMock()
    fake_user.id = 42

    find_one_or_none = AsyncMock(return_value=fake_user)
    monkeypatch.setattr(
        "api.middleware.auth_middleware.UserDAO.find_one_or_none",
        find_one_or_none,
    )

    response = await client.get(
        "/whoami",
        headers={
            "X-Telegram-Id": "123",
            "X-Internal-Secret": "test-internal-secret",
        },
    )

    assert response.json() == {"user_id": 42}
    find_one_or_none.assert_awaited_once()
