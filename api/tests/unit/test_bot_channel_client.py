"""Тесты клиента внутреннего канала api → bot (`api/bot_channel/client.py`).

Бот подменяется `httpx.MockTransport`: проверяются заголовок авторизации,
три исхода ответа бота и недоступность бота (обрыв, таймаут, не-2xx, мусор).
Главный контракт — любое «не подтверждено» это исключение, чтобы вызывающий
код не удалил запись в БД.
"""

from datetime import datetime

import httpx
import pytest
from pydantic import SecretStr

from api.app_error.base_error import BotChannelUnavailableError, VPNRevokeFailedError
from api.bot_channel.client import BotChannelClient
from api.core.config import BotChannelSettings
from api.users.schemas import SVPNConfigOut
from shared.enums.vpn_enum import VPNRevokeStatus

API_KEY = "bot-key"


def make_settings(api_key: str = API_KEY) -> BotChannelSettings:
    return BotChannelSettings.model_construct(
        url="bot",
        port=8088,
        api_key=SecretStr(api_key),
        timeout=1.0,
        connect_timeout=1.0,
    )


@pytest.fixture
def config() -> SVPNConfigOut:
    return SVPNConfigOut(
        id=1,
        file_name="cfg.conf",
        pub_key="pub",
        node_name="fr",
        backend="amnezia",
        protocol="wg_v2",
        config_ids=None,
        created_at=datetime(2026, 10, 1),
    )


def make_client(handler, api_key: str = API_KEY) -> BotChannelClient:
    return BotChannelClient(
        make_settings(api_key), transport=httpx.MockTransport(handler)
    )


@pytest.mark.parametrize("bot_status", [VPNRevokeStatus.OK, VPNRevokeStatus.NOT_FOUND])
@pytest.mark.asyncio
async def test_revoke_returns_status_and_sends_key(config, bot_status):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("X-API-Key")
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(200, json={"status": bot_status})

    result = await make_client(handler).revoke_config(tg_id=123, config=config)

    assert result == bot_status
    assert seen["key"] == API_KEY
    assert seen["path"] == "/internal/vpn/revoke"
    assert b'"tg_id":123' in seen["body"].replace(b" ", b"")
    assert b"cfg.conf" in seen["body"]


@pytest.mark.asyncio
async def test_revoke_node_error_raises_and_is_not_swallowed(config):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "node_error", "detail": "ssh down"})

    with pytest.raises(VPNRevokeFailedError) as exc_info:
        await make_client(handler).revoke_config(tg_id=1, config=config)

    assert exc_info.value.details["file_name"] == "cfg.conf"
    assert exc_info.value.details["detail"] == "ssh down"


@pytest.mark.asyncio
async def test_revoke_bot_unreachable_raises(config):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(BotChannelUnavailableError, match="нет соединения"):
        await make_client(handler).revoke_config(tg_id=1, config=config)


@pytest.mark.asyncio
async def test_revoke_bot_timeout_raises(config):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(BotChannelUnavailableError, match="таймаут"):
        await make_client(handler).revoke_config(tg_id=1, config=config)


@pytest.mark.parametrize("http_status", [401, 403, 422, 500, 502])
@pytest.mark.asyncio
async def test_revoke_non_200_raises(config, http_status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(http_status, json={"detail": "x"})

    with pytest.raises(BotChannelUnavailableError, match=str(http_status)):
        await make_client(handler).revoke_config(tg_id=1, config=config)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>nginx</html>"),
        httpx.Response(200, json={"status": "unknown"}),
        httpx.Response(200, json={}),
    ],
)
@pytest.mark.asyncio
async def test_revoke_garbage_body_raises(config, response):
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(BotChannelUnavailableError, match="нераспознаваемый"):
        await make_client(handler).revoke_config(tg_id=1, config=config)


@pytest.mark.asyncio
async def test_revoke_without_api_key_does_not_call_bot(config):
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"status": "ok"})

    with pytest.raises(BotChannelUnavailableError, match="BOT_INTERNAL_API_KEY"):
        await make_client(handler, api_key="").revoke_config(tg_id=1, config=config)

    assert called is False


@pytest.mark.asyncio
async def test_send_broadcast_returns_recipients_and_sends_key():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("X-API-Key")
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(200, json={"accepted": True, "recipients": 2})

    result = await make_client(handler).send_broadcast("Привет!", [111, 222])

    assert result == 2
    assert seen["key"] == API_KEY
    assert seen["path"] == "/internal/broadcast"
    assert b"111" in seen["body"] and b"222" in seen["body"]
    assert b"\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82" in seen["body"]


@pytest.mark.asyncio
async def test_send_broadcast_bot_unreachable_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(BotChannelUnavailableError, match="нет соединения"):
        await make_client(handler).send_broadcast("Привет!", [1])


@pytest.mark.asyncio
async def test_send_broadcast_non_200_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "x"})

    with pytest.raises(BotChannelUnavailableError, match="403"):
        await make_client(handler).send_broadcast("Привет!", [1])


@pytest.mark.asyncio
async def test_send_broadcast_without_api_key_does_not_call_bot():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"accepted": True, "recipients": 1})

    with pytest.raises(BotChannelUnavailableError, match="BOT_INTERNAL_API_KEY"):
        await make_client(handler, api_key="").send_broadcast("Привет!", [1])

    assert called is False
