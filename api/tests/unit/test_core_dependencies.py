"""Тесты api/core/dependencies.py::get_session (#236 — одна сессия на запрос)."""

from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from api.core.dependencies import get_session


class _FakeDBSessionMiddleware(BaseHTTPMiddleware):
    """Имитирует DBSessionMiddleware: кладёт мок-сессию в request.state.db."""

    def __init__(self, app, session):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._session = session

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.db = self._session
        return await call_next(request)


@pytest.fixture
def session_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def app(session_mock: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.add_middleware(_FakeDBSessionMiddleware, session=session_mock)

    @application.get("/probe")
    async def probe(session=Depends(get_session)) -> dict:  # type: ignore[no-untyped-def]
        return {"same_session": session is session_mock}

    @application.get("/boom")
    async def boom(session=Depends(get_session)) -> dict:  # type: ignore[no-untyped-def]
        raise ValueError("boom")

    return application


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_session_reuses_middleware_session(client, session_mock):
    """get_session отдаёт ту же сессию, что DBSessionMiddleware положил в
    request.state.db — не открывает вторую.
    """
    response = await client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"same_session": True}
    session_mock.commit.assert_awaited_once()
    session_mock.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_exception(client, session_mock):
    """Исключение в роуте приводит к rollback(), а не к commit()."""
    with pytest.raises(ValueError, match="boom"):
        await client.get("/boom")

    session_mock.rollback.assert_awaited_once()
    session_mock.commit.assert_not_awaited()
