import inspect
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from bot.app_error.api_error import APIClientConnectionError, APIClientHTTPError
from bot.app_error.schema import ErrorDetail
from bot.core.config import REMNAWAVE_SUBSCRIPTION_TIERS
from bot.vpn.utils.panel_protocol import PanelAdapter
from bot.vpn.utils.remnawave.adapter import RemnawaveAdapter
from bot.vpn.utils.remnawave.exceptions import (
    RemnawaveAuthError,
    RemnawaveError,
    RemnawaveInvalidExpiryError,
    RemnawaveRequestError,
    RemnawaveUserNotFoundError,
)

pytestmark = pytest.mark.vpn


def _user_envelope(
    user_id: int = 1,
    telegram_id: int = 123,
    subscription_url: str = "https://sub/x",
    expire_at: datetime | None = None,
) -> dict:
    """Собирает тело ответа панели `{"response": {...}}` с минимально обязательными полями."""
    now = datetime.now(UTC)
    return {
        "response": {
            "id": user_id,
            "shortUuid": "short-uuid",
            "username": f"u{telegram_id}_abc",
            "telegramId": telegram_id,
            "subscriptionUrl": subscription_url,
            "expireAt": (expire_at or now + timedelta(days=30)).isoformat(),
            "hwidDeviceLimit": 2,
            "activeInternalSquads": [],
            "status": "ACTIVE",
            "createdAt": now.isoformat(),
            "updatedAt": now.isoformat(),
        }
    }


def _tier_map() -> dict[str, str]:
    """tier_map, покрывающий все значения REMNAWAVE_SUBSCRIPTION_TIERS."""
    return {t: t for t in REMNAWAVE_SUBSCRIPTION_TIERS}


def _squads() -> dict[str, list]:
    return {
        "trial": [uuid4()],
        "standard": [uuid4()],
        "premium": [uuid4(), uuid4()],
        "founder": [uuid4()],
        "ultimate": [uuid4()],
    }


def _adapter(mocker, squads=None, tier_map=None):
    api_client = mocker.AsyncMock()
    adapter = RemnawaveAdapter(
        api_client,
        token="t",
        squads=squads if squads is not None else _squads(),
        tier_map=tier_map if tier_map is not None else _tier_map(),
        prefix="/api",
    )
    return adapter, api_client


# --- T-2: add_new_config ---------------------------------------------------


@pytest.mark.asyncio
async def test_add_new_config_success(mocker):
    """Валидный ответ панели -> возврат ({"remnawave": [id]}, subscription_url) и корректный payload запроса."""
    adapter, api_client = _adapter(mocker)
    api_client.post.return_value = (_user_envelope(user_id=42), 201)

    expires_at = datetime.now(UTC) + timedelta(days=5)
    ids, url = await adapter.add_new_config(
        tg_id=123,
        expires_at=expires_at,
        sub_type="standard",
        device_limit=2,
    )

    assert ids == {"remnawave": ["42"]}
    assert url == "https://sub/x"

    api_client.post.assert_awaited_once()
    call = api_client.post.call_args
    assert call.kwargs["json"]["telegramId"] == 123
    assert call.kwargs["json"]["hwidDeviceLimit"] == 2
    assert call.kwargs["json"]["activeInternalSquads"] == [
        str(u) for u in adapter.squads["standard"]
    ]
    assert call.kwargs["json"]["username"].startswith("u123_")


@pytest.mark.asyncio
async def test_add_new_config_none_expiry_uses_unlimited(mocker):
    """expires_at=None -> в payload уходит expireAt == UNLIMITED_EXPIRE_AT."""
    adapter, api_client = _adapter(mocker)
    api_client.post.return_value = (_user_envelope(user_id=1), 201)

    await adapter.add_new_config(
        tg_id=123, expires_at=None, sub_type="standard", device_limit=2
    )

    call = api_client.post.call_args
    assert (
        datetime.fromisoformat(call.kwargs["json"]["expireAt"])
        == adapter.UNLIMITED_EXPIRE_AT
    )


@pytest.mark.asyncio
async def test_add_new_config_past_expiry_raises_without_request(mocker):
    """expires_at в прошлом -> RemnawaveInvalidExpiryError, post не вызывается."""
    adapter, api_client = _adapter(mocker)

    past = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(RemnawaveInvalidExpiryError):
        await adapter.add_new_config(
            tg_id=123, expires_at=past, sub_type="standard", device_limit=2
        )

    api_client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_new_config_unknown_sub_type_raises_without_request(mocker):
    """sub_type отсутствует в tier_map -> RemnawaveError, post не вызывается."""
    adapter, api_client = _adapter(mocker)

    with pytest.raises(RemnawaveError):
        await adapter.add_new_config(
            tg_id=123,
            expires_at=datetime.now(UTC) + timedelta(days=5),
            sub_type="not_a_tier",
            device_limit=2,
        )

    api_client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_new_config_tier_map_points_to_missing_squad_raises(mocker):
    """tier_map[sub_type] указывает на отсутствующий в squads ключ -> RemnawaveError."""
    tier_map = _tier_map()
    tier_map["standard"] = "ghost_group"
    adapter, api_client = _adapter(mocker, tier_map=tier_map)

    with pytest.raises(RemnawaveError):
        await adapter.add_new_config(
            tg_id=123,
            expires_at=datetime.now(UTC) + timedelta(days=5),
            sub_type="standard",
            device_limit=2,
        )

    api_client.post.assert_not_awaited()


# --- T-3: extend_config / set_tier / delete_config / _request --------------


@pytest.mark.asyncio
async def test_delete_config_not_found_returns_false(mocker):
    """Панель отвечает 404 на delete -> delete_config возвращает False."""
    adapter, api_client = _adapter(mocker)
    api_client.delete.side_effect = APIClientHTTPError(
        404, ErrorDetail(code="not_found", message="not found")
    )

    result = await adapter.delete_config(config_id="42")

    assert result is False


@pytest.mark.asyncio
async def test_delete_config_success_returns_true(mocker):
    """Успешный delete -> delete_config возвращает True."""
    adapter, api_client = _adapter(mocker)
    api_client.delete.return_value = ({}, 200)

    result = await adapter.delete_config(config_id="42")

    assert result is True


@pytest.mark.asyncio
async def test_set_tier_valid_patches_new_squads(mocker):
    """Валидный sub_type -> patch вызван с activeInternalSquads нового тира."""
    adapter, api_client = _adapter(mocker)
    api_client.patch.return_value = (_user_envelope(user_id=42), 200)

    await adapter.set_tier(config_id="42", sub_type="premium")

    api_client.patch.assert_awaited_once()
    call = api_client.patch.call_args
    assert call.kwargs["json"]["activeInternalSquads"] == [
        str(u) for u in adapter.squads["premium"]
    ]


@pytest.mark.asyncio
async def test_set_tier_unknown_sub_type_raises_without_request(mocker):
    """Неизвестный sub_type -> RemnawaveError, patch не вызывается."""
    adapter, api_client = _adapter(mocker)

    with pytest.raises(RemnawaveError):
        await adapter.set_tier(config_id="42", sub_type="not_a_tier")

    api_client.patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_extend_config_past_expiry_raises(mocker):
    """expires_at в прошлом -> RemnawaveInvalidExpiryError."""
    adapter, api_client = _adapter(mocker)

    past = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(RemnawaveInvalidExpiryError):
        await adapter.extend_config(config_ids=["42"], expires_at=past)

    api_client.get.assert_not_awaited()
    api_client.patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_extend_config_patches_found_users_and_skips_missing(mocker):
    """Валидный expires_at: найденные config_id продлеваются, не найденный (404) пропускается без patch."""
    adapter, api_client = _adapter(mocker)

    async def get_side_effect(path, **kwargs):
        if path.endswith("/43"):
            raise APIClientHTTPError(404, ErrorDetail(code="not_found", message="nf"))
        return _user_envelope(user_id=42), 200

    api_client.get.side_effect = get_side_effect
    api_client.patch.return_value = (_user_envelope(user_id=42), 200)

    new_expiry = datetime.now(UTC) + timedelta(days=10)
    result = await adapter.extend_config(config_ids=["42", "43"], expires_at=new_expiry)

    assert result == ["42"]
    api_client.patch.assert_awaited_once()


@pytest.mark.parametrize(
    "status_code,expected_exc",
    [
        (401, RemnawaveAuthError),
        (403, RemnawaveAuthError),
        (404, RemnawaveUserNotFoundError),
        (400, RemnawaveRequestError),
        (500, RemnawaveRequestError),
    ],
)
@pytest.mark.asyncio
async def test_request_maps_http_status_to_exception(mocker, status_code, expected_exc):
    """_request маппит HTTP статус панели в соответствующее доменное исключение."""
    adapter, api_client = _adapter(mocker)
    api_client.get.side_effect = APIClientHTTPError(
        status_code, ErrorDetail(code="err", message="boom")
    )

    with pytest.raises(expected_exc):
        await adapter._request("GET", "/api/users/1")


@pytest.mark.asyncio
async def test_request_other_4xx_5xx_preserves_status_code(mocker):
    """Произвольный 4xx/5xx (не 401/403/404) -> RemnawaveRequestError с тем же status_code."""
    adapter, api_client = _adapter(mocker)
    api_client.get.side_effect = APIClientHTTPError(
        400, ErrorDetail(code="err", message="boom")
    )

    with pytest.raises(RemnawaveRequestError) as exc:
        await adapter._request("GET", "/api/users/1")

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_request_connection_error_maps_to_502(mocker):
    """APIClientConnectionError -> RemnawaveRequestError со status_code == 502."""
    adapter, api_client = _adapter(mocker)
    api_client.get.side_effect = APIClientConnectionError()

    with pytest.raises(RemnawaveRequestError) as exc:
        await adapter._request("GET", "/api/users/1")

    assert exc.value.status_code == 502


def test_remnawave_adapter_satisfies_panel_protocol():
    """RemnawaveAdapter реализует все методы PanelAdapter как корутины с теми же параметрами."""
    panel_methods = {
        name
        for name in dir(PanelAdapter)
        if not name.startswith("_") and inspect.isfunction(getattr(PanelAdapter, name))
    }
    # PanelAdapter — обычный Protocol (не runtime_checkable), поэтому isinstance
    # невозможен; сверяем структурно по сигнатурам. Пустое множество означало бы,
    # что Protocol отрефакторили и тест молча перестал что-либо проверять.
    assert panel_methods == {"extend_config", "set_unlimited_config", "delete_config"}

    for name in panel_methods:
        impl = getattr(RemnawaveAdapter, name, None)
        assert impl is not None, f"RemnawaveAdapter не реализует {name}"
        assert inspect.iscoroutinefunction(impl), f"{name} должен быть async"
        proto_params = list(inspect.signature(getattr(PanelAdapter, name)).parameters)
        impl_params = list(inspect.signature(impl).parameters)
        assert impl_params == proto_params, f"сигнатура {name} разошлась с Protocol"
