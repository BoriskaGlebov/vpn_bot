import json
from decimal import Decimal

import httpx
import pytest
from starlette.datastructures import Headers

from bot.payment.dto import CreatedPaymentDTO, CreatePaymentDTO, PaymentStatus
from bot.payment.exceptions import PaymentProviderError
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
async def test_create_payment_success_maps_response():
    """Успешное создание платежа: payload запроса и маппинг ответа Platega в DTO.

    Единственный метод, реально обращающийся к платёжному шлюзу — раньше был
    вообще без тестов, несмотря на то что это прямой денежный путь.
    """
    provider = make_provider()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/transaction/process"
        body = json.loads(request.content)
        assert body["paymentDetails"]["amount"] == 100.0
        assert body["paymentDetails"]["currency"] == "RUB"
        assert body["payload"] == "order-1"
        return httpx.Response(
            status_code=200,
            json={
                "status": "pending",
                "transactionId": "prov-tx-1",
                "url": "https://pay.platega.io/abc",
                "expiresIn": "2026-01-01T00:00:00Z",
                "rate": 1.0,
            },
        )

    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=PlategaProvider.BASE_URL
    )

    result = await provider.create_payment(
        data=CreatePaymentDTO(
            amount=Decimal(100),
            currency="RUB",
            order_id="order-1",
            description="test payment",
        )
    )

    assert isinstance(result, CreatedPaymentDTO)
    assert result.provider_payment_id == "prov-tx-1"
    assert result.payment_url == "https://pay.platega.io/abc"
    assert result.status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_create_payment_http_error_wrapped_in_domain_error():
    """HTTP-ошибка Platega оборачивается в PaymentProviderError (AppError).

    Раньше пробрасывался голый httpx.HTTPError, который не наследует
    AppError и не попадает в ErrorHandlerMiddleware — превращался в generic
    "unexpected_error" вместо понятной доменной ошибки.
    """
    provider = make_provider()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, json={"error": "internal"})

    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=PlategaProvider.BASE_URL
    )

    with pytest.raises(PaymentProviderError) as exc_info:
        await provider.create_payment(
            data=CreatePaymentDTO(
                amount=Decimal(100),
                currency="RUB",
                order_id="order-1",
                description="test payment",
            )
        )

    assert "order-1" in str(exc_info.value)
    assert isinstance(exc_info.value.cause, httpx.HTTPError)


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


@pytest.mark.asyncio
async def test_parse_webhook_maps_unknown_status_to_pending():
    """Незнакомый provider_status трактуется как PENDING, а не падает/теряется.

    Новый/неучтённый статус от Platega не должен приводить к падению
    обработки вебхука — по коду это осознанный fallback, но раньше он не был
    закреплён тестом.
    """
    provider = make_provider()

    event = await provider.parse_webhook(b'{"id": "tx-4", "status": "SOME_NEW_STATUS"}')

    assert event.status == PaymentStatus.PENDING
    assert event.raw_data["status"] == "SOME_NEW_STATUS"
