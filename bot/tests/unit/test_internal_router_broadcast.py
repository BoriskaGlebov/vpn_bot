"""Эндпоинт рассылки внутреннего канала api → bot (`POST /internal/broadcast`, #385).

Авторизация (`X-API-Key`) уже покрыта `test_internal_router.py` для соседнего
эндпоинта на том же роутере с теми же зависимостями — здесь не дублируется,
проверяется один негативный случай плюс контракт самого эндпоинта: запуск
рассылки в фоне не блокирует ответ, а её падение не превращается в 5xx.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from bot.app_error.base_error import AppError
from bot.core.config import settings_bot
from bot.core.exceptions.handlers import app_error_handler
from bot.internal.dependencies import get_admin_broadcast_service
from bot.internal.router import router
from bot.news.services import BroadcastService

API_KEY = "test-internal-api-key"
URL = "/internal/broadcast"


@pytest.fixture(autouse=True)
def internal_key(monkeypatch):
    """Включает канал: задаёт ключ в настройках бота."""
    monkeypatch.setattr(settings_bot.bot, "internal_api_key", SecretStr(API_KEY))


@pytest.fixture
def broadcast_service_mock():
    return AsyncMock(spec=BroadcastService)


@pytest.fixture
def app(broadcast_service_mock):
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    fastapi_app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    fastapi_app.dependency_overrides[get_admin_broadcast_service] = (
        lambda: broadcast_service_mock
    )
    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.bot
@pytest.mark.asyncio
async def test_broadcast_without_key_returns_401(client, broadcast_service_mock):
    response = await client.post(URL, json={"text": "hi", "recipients": [1]})

    assert response.status_code == 401
    broadcast_service_mock.broadcast_to_all.assert_not_called()


@pytest.mark.bot
@pytest.mark.asyncio
async def test_broadcast_accepted_response_does_not_wait_for_completion(
    client, broadcast_service_mock
):
    """Ответ «принято» уходит сразу — рассылка запускается в фоне."""
    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow_broadcast(*args, **kwargs):
        started.set()
        await finished.wait()
        return 3, 0

    broadcast_service_mock.broadcast_to_all.side_effect = slow_broadcast

    response = await client.post(
        URL,
        json={"text": "Привет!", "recipients": [1, 2, 3]},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "recipients": 3}
    await asyncio.wait_for(started.wait(), timeout=1)

    finished.set()
    await asyncio.sleep(0)


@pytest.mark.bot
@pytest.mark.asyncio
async def test_broadcast_passes_text_and_recipients_to_service(
    client, broadcast_service_mock
):
    response = await client.post(
        URL,
        json={"text": "Привет!", "recipients": [1, 2, 3]},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 200
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    broadcast_service_mock.broadcast_to_all.assert_awaited_once()
    kwargs = broadcast_service_mock.broadcast_to_all.await_args.kwargs
    assert kwargs["content"] == {"content_type": "text", "text": "Привет!"}
    assert kwargs["recipients"] == [1, 2, 3]
    assert kwargs["notify_always"] is True
    assert kwargs["preview"] == "Привет!"


@pytest.mark.bot
@pytest.mark.asyncio
async def test_broadcast_empty_text_returns_422(client, broadcast_service_mock):
    response = await client.post(
        URL,
        json={"text": "", "recipients": [1]},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 422
    broadcast_service_mock.broadcast_to_all.assert_not_called()


@pytest.mark.bot
@pytest.mark.asyncio
async def test_broadcast_empty_recipients_returns_422(client, broadcast_service_mock):
    response = await client.post(
        URL,
        json={"text": "hi", "recipients": []},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 422
    broadcast_service_mock.broadcast_to_all.assert_not_called()


@pytest.mark.bot
@pytest.mark.asyncio
async def test_broadcast_background_failure_does_not_affect_response(
    client, broadcast_service_mock
):
    """Падение фоновой задачи (напр., TelegramForbiddenError у части получателей
    внутри `BroadcastService`) не должно превращать уже отданный ответ в ошибку —
    `run_in_background` логирует и глушит исключение, а не пробрасывает его.
    """
    broadcast_service_mock.broadcast_to_all.side_effect = RuntimeError("boom")

    response = await client.post(
        URL,
        json={"text": "hi", "recipients": [1]},
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 200
    await asyncio.sleep(0)
    await asyncio.sleep(0)
