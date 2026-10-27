"""Контрактные тесты внутреннего канала api → bot (`bot/internal/router.py`).

Роутер поднимается изолированно, `VPNService` подменяется через
`dependency_overrides` (как в `test_payment_router.py`). Проверяются
авторизация по `X-API-Key` (нет ключа / неверный / канал выключен) и три
исхода отзыва доступа: ok / not_found / node_error.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from bot.app_error.base_error import VPNConfigDeletionFailedError
from bot.core.config import settings_bot
from bot.internal.dependencies import get_vpn_service
from bot.internal.router import router
from bot.vpn.services import VPNService
from shared.enums.vpn_enum import VPNRevokeStatus

API_KEY = "test-internal-api-key"
URL = "/internal/vpn/revoke"


@pytest.fixture(autouse=True)
def internal_key(monkeypatch):
    """Включает канал: задаёт ключ в настройках бота."""
    monkeypatch.setattr(settings_bot.bot, "internal_api_key", SecretStr(API_KEY))


@pytest.fixture
def vpn_service_mock():
    return AsyncMock(spec=VPNService)


@pytest.fixture
def app(vpn_service_mock):
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    fastapi_app.dependency_overrides[get_vpn_service] = lambda: vpn_service_mock
    return fastapi_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def payload() -> dict:
    return {
        "tg_id": 123,
        "config": {
            "id": 1,
            "file_name": "cfg.conf",
            "pub_key": "pub",
            "node_name": "fr",
            "backend": "amnezia",
            "protocol": "wg_v2",
            "config_ids": None,
            "created_at": datetime(2026, 10, 1).isoformat(),
        },
    }


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_without_key_returns_401(client, vpn_service_mock, payload):
    response = await client.post(URL, json=payload)

    assert response.status_code == 401
    vpn_service_mock.revoke_config_access.assert_not_awaited()


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_with_wrong_key_returns_401(client, vpn_service_mock, payload):
    response = await client.post(URL, json=payload, headers={"X-API-Key": "wrong"})

    assert response.status_code == 401
    vpn_service_mock.revoke_config_access.assert_not_awaited()


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_when_channel_disabled_returns_403(
    client, vpn_service_mock, payload, monkeypatch
):
    """Пустой ключ в конфиге выключает канал — даже «правильный» пустой не пройдёт."""
    monkeypatch.setattr(settings_bot.bot, "internal_api_key", SecretStr(""))

    response = await client.post(URL, json=payload, headers={"X-API-Key": ""})

    assert response.status_code == 403
    vpn_service_mock.revoke_config_access.assert_not_awaited()


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_ok(client, vpn_service_mock, payload):
    vpn_service_mock.revoke_config_access.return_value = True

    response = await client.post(URL, json=payload, headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    assert response.json()["status"] == VPNRevokeStatus.OK
    vpn_service_mock.revoke_config_access.assert_awaited_once()
    revoked_config = vpn_service_mock.revoke_config_access.await_args.args[0]
    assert revoked_config.file_name == "cfg.conf"
    assert revoked_config.node_name == "fr"


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_not_found(client, vpn_service_mock, payload):
    vpn_service_mock.revoke_config_access.return_value = False

    response = await client.post(URL, json=payload, headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    assert response.json()["status"] == VPNRevokeStatus.NOT_FOUND


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_node_error(client, vpn_service_mock, payload):
    vpn_service_mock.revoke_config_access.side_effect = VPNConfigDeletionFailedError(
        file_name="cfg.conf"
    )

    response = await client.post(URL, json=payload, headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == VPNRevokeStatus.NODE_ERROR
    assert "cfg.conf" in body["detail"]


@pytest.mark.bot
@pytest.mark.asyncio
async def test_revoke_invalid_body_returns_422(client, vpn_service_mock):
    response = await client.post(URL, json={"tg_id": 1}, headers={"X-API-Key": API_KEY})

    assert response.status_code == 422
    vpn_service_mock.revoke_config_access.assert_not_awaited()
