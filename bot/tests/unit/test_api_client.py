from collections.abc import Awaitable, Callable

import httpx
import pytest

from bot.app_error.api_error import APIClientConnectionError
from bot.integrations.api_client import APIClient


def _make_client(
    handler: Callable[[httpx.Request], Awaitable[httpx.Response]],
    **kwargs: object,
) -> APIClient:
    transport = httpx.MockTransport(handler)
    client = APIClient(base_url="test", port=8000, retry_delay=0, **kwargs)
    client._client = httpx.AsyncClient(transport=transport, base_url=client.base_url)
    return client


@pytest.mark.asyncio
async def test_get_retries_on_read_timeout() -> None:
    """GET — идемпотентный метод, таймаут на чтение можно безопасно повторить."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"ok": True})

    client = _make_client(handler)
    try:
        data = await client.get("/ping")
    finally:
        await client.close()

    assert data == {"ok": True}
    assert calls == 2


@pytest.mark.asyncio
async def test_post_does_not_retry_on_read_timeout() -> None:
    """POST при ReadTimeout мог уже дойти до сервера — повтор запрещён."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = _make_client(handler, max_retries=3)
    try:
        with pytest.raises(APIClientConnectionError):
            await client.post("/transactions", json={})
    finally:
        await client.close()

    assert calls == 1


@pytest.mark.asyncio
async def test_post_retries_on_connect_error() -> None:
    """ConnectError гарантирует, что запрос не ушёл — повтор безопасен всегда."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused", request=request)

    client = _make_client(handler, max_retries=3)
    try:
        with pytest.raises(APIClientConnectionError):
            await client.post("/transactions", json={})
    finally:
        await client.close()

    assert calls == 3
