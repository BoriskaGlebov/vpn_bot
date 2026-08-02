import pytest
from starlette.datastructures import Headers

from bot.payment.dto import PaymentStatus
from bot.payment.providers.platega import PlategaProvider


def make_asgi_headers(pairs: dict[str, str]) -> Headers:
    """Собирает `Headers`, как их формирует ASGI-сервер (uvicorn) — имена
    заголовков приходят в нижнем регистре, а не как их прислал клиент.
    """
    raw = [(k.lower().encode(), v.encode()) for k, v in pairs.items()]
    return Headers(raw=raw)


def make_provider() -> PlategaProvider:
    return PlategaProvider(merchant_id="merchant-1", secret_key="secret-1")


@pytest.mark.asyncio
async def test_verify_webhook_accepts_real_asgi_headers():
    """Регрессия: `dict(request.headers)` схлопывает регистр заголовков
    (starlette хранит их в нижнем регистре), из-за чего настоящий вебхук от
    Platega с `X-MerchantId`/`X-Secret` всегда отклонялся как поддельный.
    `verify_webhook` должен принимать `Headers`/любой `Mapping` напрямую.
    """
    provider = make_provider()
    headers = make_asgi_headers({"X-MerchantId": "merchant-1", "X-Secret": "secret-1"})

    assert await provider.verify_webhook(headers=headers, body=b"{}") is True


@pytest.mark.asyncio
async def test_verify_webhook_rejects_missing_headers():
    provider = make_provider()
    headers = make_asgi_headers({})

    assert await provider.verify_webhook(headers=headers, body=b"{}") is False


@pytest.mark.asyncio
async def test_verify_webhook_rejects_wrong_secret():
    provider = make_provider()
    headers = make_asgi_headers({"X-MerchantId": "merchant-1", "X-Secret": "wrong"})

    assert await provider.verify_webhook(headers=headers, body=b"{}") is False


@pytest.mark.asyncio
async def test_parse_webhook_maps_confirmed_to_paid():
    provider = make_provider()
    event = await provider.parse_webhook(
        b'{"id": "tx-1", "status": "CONFIRMED", "amount": 100, "currency": "RUB"}'
    )

    assert event.provider_payment_id == "tx-1"
    assert event.status == PaymentStatus.PAID


@pytest.mark.asyncio
async def test_parse_webhook_maps_canceled_and_chargebacked_to_failed():
    provider = make_provider()

    canceled = await provider.parse_webhook(b'{"id": "tx-2", "status": "CANCELED"}')
    chargebacked = await provider.parse_webhook(
        b'{"id": "tx-3", "status": "CHARGEBACKED"}'
    )

    assert canceled.status == PaymentStatus.FAILED
    assert canceled.raw_data["status"] == "CANCELED"
    assert chargebacked.status == PaymentStatus.FAILED
    assert chargebacked.raw_data["status"] == "CHARGEBACKED"
