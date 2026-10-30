from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from bot.payment.dto import CreatedPaymentDTO
from bot.payment.schemas import SPaymentTransactionResponse
from bot.payment.services import PaymentService
from shared.enums.payment_enum import PaymentStatus


def make_tx_response(**overrides) -> SPaymentTransactionResponse:
    defaults = dict(
        id=uuid4(),
        user_id=1,
        tg_id=123,
        amount=1000,
        currency="RUB",
        status=PaymentStatus.PENDING,
        source="GATEWAY",
        subscription_months=3,
        is_premium=False,
        is_founder=False,
        description=None,
        created_by_admin_id=None,
        confirmed_by_admin_id=None,
        gateway_transaction_id=None,
        confirmed_at=None,
        paid_at=None,
    )
    defaults.update(overrides)
    return SPaymentTransactionResponse(**defaults)


@pytest.fixture
def payment_service() -> tuple[PaymentService, AsyncMock, AsyncMock]:
    adapter = AsyncMock()
    provider = AsyncMock()
    return PaymentService(adapter=adapter, provider=provider), adapter, provider


@pytest.mark.asyncio
async def test_create_transaction_passes_promo_code_to_adapter(payment_service):
    """`promo_code` доходит до api/ через адаптер — без него скидку
    было бы невозможно применить на уровне транзакции.
    """
    service, adapter, provider = payment_service
    tx_id = uuid4()
    adapter.create_transaction.return_value = make_tx_response(id=tx_id, amount=900)
    adapter.attach_provider_payment.return_value = make_tx_response(
        id=tx_id, amount=900
    )
    provider.create_payment.return_value = CreatedPaymentDTO(
        provider_payment_id="prov_1",
        payment_url="https://pay.example/1",
        status=PaymentStatus.PENDING,
    )

    await service.create_transaction(
        amount=1000,
        subscription_months=3,
        is_premium=False,
        is_founder=False,
        promo_code="SALE10",
    )

    adapter.create_transaction.assert_awaited_once_with(
        amount=1000,
        subscription_months=3,
        is_premium=False,
        is_founder=False,
        promo_code="SALE10",
    )


@pytest.mark.asyncio
async def test_create_transaction_charges_discounted_amount_at_provider(
    payment_service,
):
    """Провайдеру должна запрашиваться итоговая (дисконтированная) сумма
    из ответа api/, а не исходная база — иначе клиент оплатит полную цену,
    хотя в БД записана сумма со скидкой, и сверка вебхука
    (`_amount_matches_expected`) не совпадёт.
    """
    service, adapter, provider = payment_service
    tx_id = uuid4()
    # api/ пересчитал сумму со скидкой: 1000 (база) -> 900 (после промокода).
    adapter.create_transaction.return_value = make_tx_response(id=tx_id, amount=900)
    adapter.attach_provider_payment.return_value = make_tx_response(
        id=tx_id, amount=900
    )
    provider.create_payment.return_value = CreatedPaymentDTO(
        provider_payment_id="prov_1",
        payment_url="https://pay.example/1",
        status=PaymentStatus.PENDING,
    )

    await service.create_transaction(
        amount=1000,
        subscription_months=3,
        is_premium=False,
        is_founder=False,
        promo_code="SALE10",
    )

    provider.create_payment.assert_awaited_once()
    payment_data = provider.create_payment.await_args.kwargs["data"]
    assert payment_data.amount == 900


@pytest.mark.asyncio
async def test_create_transaction_without_promo_uses_full_amount(payment_service):
    """Без промокода api/ возвращает ту же сумму — провайдер получает её."""
    service, adapter, provider = payment_service
    tx_id = uuid4()
    adapter.create_transaction.return_value = make_tx_response(id=tx_id, amount=1000)
    adapter.attach_provider_payment.return_value = make_tx_response(
        id=tx_id, amount=1000
    )
    provider.create_payment.return_value = CreatedPaymentDTO(
        provider_payment_id="prov_1",
        payment_url="https://pay.example/1",
        status=PaymentStatus.PENDING,
    )

    await service.create_transaction(
        amount=1000,
        subscription_months=3,
        is_premium=False,
        is_founder=False,
    )

    adapter.create_transaction.assert_awaited_once_with(
        amount=1000,
        subscription_months=3,
        is_premium=False,
        is_founder=False,
        promo_code=None,
    )
    payment_data = provider.create_payment.await_args.kwargs["data"]
    assert payment_data.amount == 1000
