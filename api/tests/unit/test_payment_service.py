from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from api.app_error.base_error import (
    PaymentAlreadyProcessedError,
    PaymentTransactionNotFoundError,
    ReferralBonusAlreadyGivenError,
)
from api.payment.dao import PaymentTransactionDAO
from api.payment.model import PaymentSource, PaymentStatus, PaymentTransaction
from api.payment.schemas import (
    SCreateTransaction,
    SGatewayTransactionFilter,
    SPaidAt,
    SPaymentStatusCancel,
    SPaymentStatusUpdate,
    STransactionIDFilter,
    SYearIncome,
)
from api.payment.services import PaymentService


@pytest.fixture
def payment_service() -> PaymentService:
    return PaymentService(
        sub_service=AsyncMock(),
        ref_service=AsyncMock(),
    )


@pytest.fixture
def mock_transaction() -> Mock:
    return Mock(spec=PaymentTransaction)


@pytest.mark.asyncio
async def test_get_transaction_or_raise_success(
    payment_service,
    mock_session,
    mock_transaction,
):
    transaction_id = uuid4()

    with patch.object(
        PaymentTransactionDAO,
        "find_one_or_none_by_id",
        new=AsyncMock(return_value=mock_transaction),
    ) as mock_find:
        result = await payment_service._get_transaction_or_raise(
            session=mock_session,
            transaction_id=transaction_id,
        )

    assert result is mock_transaction

    mock_find.assert_awaited_once_with(
        session=mock_session,
        data_id=transaction_id,
    )


@pytest.mark.asyncio
async def test_get_transaction_or_raise_not_found(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    with patch.object(
        PaymentTransactionDAO,
        "find_one_or_none_by_id",
        new=AsyncMock(return_value=None),
    ) as mock_find:
        with pytest.raises(PaymentTransactionNotFoundError):
            await payment_service._get_transaction_or_raise(
                session=mock_session,
                transaction_id=transaction_id,
            )

    mock_find.assert_awaited_once_with(
        session=mock_session,
        data_id=transaction_id,
    )


def test_ensure_pending_ok(payment_service):
    tx = Mock()
    tx.status = PaymentStatus.PENDING

    # не должно падать
    payment_service._ensure_pending(tx)


def test_ensure_pending_raises(payment_service):
    tx = Mock()
    tx.id = "test-id"
    tx.status = PaymentStatus.PAID  # любой НЕ PENDING

    with pytest.raises(PaymentAlreadyProcessedError) as exc:
        payment_service._ensure_pending(tx)
    assert exc.value.details.get("transaction_id") == str(tx.id)
    assert exc.value.details.get("status") == tx.status


@pytest.mark.asyncio
async def test_create_transaction_success(
    payment_service,
    mock_session,
):
    user = Mock()
    user.id = 10

    transaction_data = Mock()
    transaction_data.model_dump.return_value = {
        "amount": 1000,
        "currency": "RUB",
        "subscription_months": 3,
        "is_premium": True,
        "is_founder": False,
        "description": "test",
    }

    db_result = Mock(spec=PaymentTransaction)
    db_result.id = uuid4()
    db_result.to_dict.return_value = {
        "id": str(db_result.id),
        "user_id": 10,
        "amount": 1000,
    }

    with patch.object(
        PaymentTransactionDAO,
        "add",
        new=AsyncMock(return_value=db_result),
    ) as mock_add:

        result = await payment_service.create_transaction(
            session=mock_session,
            transaction=transaction_data,
            user_auth=user,
        )

    # DAO вызов
    mock_add.assert_awaited_once()

    call_args = mock_add.call_args.kwargs
    assert call_args["session"] == mock_session

    # проверяем schema
    schema = call_args["values"]
    assert isinstance(schema, SCreateTransaction)
    assert schema.user_id == 10

    # данные из transaction.model_dump должны попасть в schema
    assert schema.amount == 1000
    assert schema.currency == "RUB"
    assert schema.subscription_months == 3
    assert schema.is_premium is True

    # результат
    assert result is not None


@pytest.mark.asyncio
async def test_get_by_gateway_id_success(
    payment_service,
    mock_session,
):
    gateway_id = "bd3ba8d9-b027-446d-aec1-9cdd118925c7"

    db_tx = Mock(spec=PaymentTransaction)
    db_tx.id = uuid4()
    db_tx.to_dict.return_value = {
        "id": db_tx.id,
        "user_id": 1,
        "tg_id": 123,
        "amount": 100,
        "currency": "RUB",
        "status": "PAID",
        "source": "GATEWAY",
        "subscription_months": 3,
        "is_premium": False,
        "is_founder": False,
        "description": None,
        "created_by_admin_id": None,
        "confirmed_by_admin_id": None,
        "gateway_transaction_id": gateway_id,
        "confirmed_at": None,
        "paid_at": None,
    }

    with patch.object(
        PaymentTransactionDAO,
        "find_one_or_none",
        new=AsyncMock(return_value=db_tx),
    ) as mock_find:

        result = await payment_service.get_by_gateway_id(
            session=mock_session,
            gateway_transaction_id=gateway_id,
        )

    # DAO вызов
    mock_find.assert_awaited_once()

    call_kwargs = mock_find.call_args.kwargs
    assert call_kwargs["session"] == mock_session

    assert isinstance(call_kwargs["filters"], SGatewayTransactionFilter)
    assert call_kwargs["filters"].gateway_transaction_id == gateway_id

    # результат
    assert result.gateway_transaction_id == gateway_id
    assert result.id == db_tx.id


@pytest.mark.asyncio
async def test_get_by_gateway_id_not_found(
    payment_service,
    mock_session,
):
    gateway_id = "bd3ba8d9-b027-446d-aec1-9cdd118925c7"

    with patch.object(
        PaymentTransactionDAO,
        "find_one_or_none",
        new=AsyncMock(return_value=None),
    ) as mock_find:

        with pytest.raises(PaymentTransactionNotFoundError) as exc:
            await payment_service.get_by_gateway_id(
                session=mock_session,
                gateway_transaction_id=gateway_id,
            )

    mock_find.assert_awaited_once()

    assert exc.value.details.get("gateway_transaction_id") == gateway_id


@pytest.mark.asyncio
async def test_attach_provider_payment_success(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    gateway_info = Mock()
    gateway_info.gateway_transaction_id = "gw_123"
    gateway_info.gateway_payload = {"key": "value"}
    gateway_info.source = "GATEWAY"

    updated_tx = Mock(spec=PaymentTransaction)
    updated_tx.to_dict.return_value = {
        "id": str(transaction_id),
        "gateway_transaction_id": "gw_123",
        "user_id": 1,
        "tg_id": 123,
        "amount": 100,
        "currency": "RUB",
        "status": "PENDING",
        "source": "GATEWAY",
        "subscription_months": 1,
        "is_premium": False,
        "is_founder": False,
        "description": None,
        "created_by_admin_id": None,
        "confirmed_by_admin_id": None,
        "confirmed_at": None,
        "paid_at": None,
    }

    with (
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=1),
        ) as mock_update,
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=updated_tx),
        ) as mock_get,
    ):

        result = await payment_service.attach_provider_payment(
            session=mock_session,
            transaction_id=transaction_id,
            gateway_info=gateway_info,
        )

    # update вызван корректно
    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs

    assert call_kwargs["session"] == mock_session
    assert isinstance(call_kwargs["filters"], STransactionIDFilter)
    assert call_kwargs["filters"].id == transaction_id
    assert call_kwargs["values"] == gateway_info

    # после update вызвали fetch
    mock_get.assert_awaited_once_with(
        session=mock_session,
        transaction_id=transaction_id,
    )

    # результат
    assert result.gateway_transaction_id == "gw_123"


@pytest.mark.asyncio
async def test_attach_provider_payment_not_found(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    gateway_info = Mock()
    gateway_info.gateway_transaction_id = "gw_missing"
    gateway_info.gateway_payload = None
    gateway_info.source = "GATEWAY"

    with (
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=0),
        ) as mock_update,
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(),
        ) as mock_get,
    ):

        with pytest.raises(PaymentTransactionNotFoundError) as exc:
            await payment_service.attach_provider_payment(
                session=mock_session,
                transaction_id=transaction_id,
                gateway_info=gateway_info,
            )

    mock_update.assert_awaited_once()

    # важно: после failed update не идём в fetch
    mock_get.assert_not_awaited()

    assert exc.value.details.get("transaction_id") == str(transaction_id)
    assert exc.value.details.get("gateway_transaction_id") == "gw_missing"


@pytest.mark.asyncio
async def test_mark_payment_started_success(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()
    fixed_time = datetime(2024, 1, 1, 12, 0, 0)

    updated_tx = Mock(spec=PaymentTransaction)
    updated_tx.to_dict.return_value = {
        "id": transaction_id,
        "paid_at": fixed_time.isoformat(),
        "status": "PENDING",
        "user_id": 1,
        "tg_id": 123,
        "amount": 100,
        "currency": "RUB",
        "subscription_months": 1,
        "is_premium": False,
        "is_founder": False,
        "description": None,
        "source": "GATEWAY",
    }

    with (
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=1),
        ) as mock_update,
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=updated_tx),
        ) as mock_get,
        patch(
            "api.payment.services.datetime",
        ) as mock_datetime,
    ):

        mock_datetime.now.return_value = fixed_time

        result = await payment_service.mark_payment_started(
            session=mock_session,
            transaction_id=transaction_id,
        )

    mock_update.assert_awaited_once()

    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["session"] == mock_session
    assert isinstance(call_kwargs["filters"], STransactionIDFilter)

    # важно: проверяем фиксированное время
    assert isinstance(call_kwargs["values"], SPaidAt)
    assert call_kwargs["values"].paid_at == fixed_time

    mock_get.assert_awaited_once()

    assert result.id == transaction_id


@pytest.mark.asyncio
async def test_mark_payment_started_not_found(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    with (
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=0),
        ) as mock_update,
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(),
        ) as mock_get,
    ):

        with pytest.raises(PaymentTransactionNotFoundError) as exc:
            await payment_service.mark_payment_started(
                session=mock_session,
                transaction_id=transaction_id,
            )

    mock_update.assert_awaited_once()
    mock_get.assert_not_awaited()

    assert exc.value.details.get("transaction_id") == str(transaction_id)


@pytest.mark.asyncio
async def test_admin_confirm_transaction_success(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    data = Mock()
    data.id = transaction_id
    data.admin_id = 99

    tx = Mock(spec=PaymentTransaction)
    tx.status = PaymentStatus.PENDING
    tx.to_dict.return_value = {
        "id": str(transaction_id),
        "status": "PAID",
        "confirmed_by_admin_id": 99,
    }

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=tx),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
            return_value=None,
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=1),
        ) as mock_update,
        patch.object(
            mock_session,
            "refresh",
            new=AsyncMock(),
        ) as mock_refresh,
    ):

        result = await payment_service.admin_confirm_transaction(
            data=data,
            session=mock_session,
        )

    # verify flow order
    mock_get.assert_awaited_once()
    mock_pending.assert_called_once_with(tx=tx)

    mock_update.assert_awaited_once()

    call_kwargs = mock_update.call_args.kwargs
    assert isinstance(call_kwargs["filters"], STransactionIDFilter)
    assert call_kwargs["filters"].id == transaction_id

    values = call_kwargs["values"]
    assert isinstance(values, SPaymentStatusUpdate)
    assert values.status == PaymentStatus.PAID
    assert values.confirmed_by_admin_id == 99
    assert values.source == PaymentSource.MANUAL

    mock_refresh.assert_awaited_once_with(tx)

    assert result is not None


@pytest.mark.asyncio
async def test_admin_confirm_transaction_not_found(
    payment_service,
    mock_session,
):
    data = Mock()
    data.id = uuid4()
    data.admin_id = 1

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(
                side_effect=PaymentTransactionNotFoundError(
                    transaction_id="123", gateway_transaction_id="123"
                )
            ),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(),
        ) as mock_update,
    ):

        with pytest.raises(PaymentTransactionNotFoundError):
            await payment_service.admin_confirm_transaction(
                data=data,
                session=mock_session,
            )

    mock_get.assert_awaited_once()
    mock_pending.assert_not_called()
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_admin_confirm_transaction_not_pending(
    payment_service,
    mock_session,
):
    data = Mock()
    data.id = uuid4()
    data.admin_id = 1

    tx = Mock(spec=PaymentTransaction)

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=tx),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
            side_effect=PaymentAlreadyProcessedError(
                transaction_id="test_id", payment_status=PaymentStatus.PAID
            ),
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(),
        ) as mock_update,
    ):

        with pytest.raises(PaymentAlreadyProcessedError):
            await payment_service.admin_confirm_transaction(
                data=data,
                session=mock_session,
            )

    mock_get.assert_awaited_once()
    mock_pending.assert_called_once_with(tx=tx)

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_confirm_transaction_success(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    data = Mock()
    data.id = transaction_id

    tx = Mock(spec=PaymentTransaction)
    tx.status = PaymentStatus.PENDING
    tx.to_dict.return_value = {
        "id": str(transaction_id),
        "status": "PAID",
        "source": "GATEWAY",
    }

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=tx),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
            return_value=None,
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=1),
        ) as mock_update,
        patch.object(
            mock_session,
            "refresh",
            new=AsyncMock(),
        ) as mock_refresh,
        patch(
            "api.payment.services.datetime",
        ) as mock_datetime,
    ):

        fixed_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = fixed_time

        result = await payment_service.webhook_confirm_transaction(
            data=data,
            session=mock_session,
        )

    # flow order
    mock_get.assert_awaited_once()
    mock_pending.assert_called_once_with(tx=tx)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs

    assert isinstance(call_kwargs["filters"], STransactionIDFilter)
    assert call_kwargs["filters"].id == transaction_id

    values = call_kwargs["values"]
    assert isinstance(values, SPaymentStatusUpdate)

    assert values.status == PaymentStatus.PAID
    assert values.source == PaymentSource.GATEWAY
    assert values.paid_at == fixed_time
    assert values.confirmed_at == fixed_time

    mock_refresh.assert_awaited_once_with(tx)

    assert result is not None


@pytest.mark.asyncio
async def test_webhook_confirm_transaction_not_found(
    payment_service,
    mock_session,
):
    data = Mock()
    data.id = uuid4()

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(
                side_effect=PaymentTransactionNotFoundError(
                    transaction_id="test_id", gateway_transaction_id="test_id"
                )
            ),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(),
        ) as mock_update,
    ):

        with pytest.raises(PaymentTransactionNotFoundError):
            await payment_service.webhook_confirm_transaction(
                data=data,
                session=mock_session,
            )

    mock_get.assert_awaited_once()
    mock_pending.assert_not_called()
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_confirm_transaction_not_pending(
    payment_service,
    mock_session,
):
    data = Mock()
    data.id = uuid4()

    tx = Mock(spec=PaymentTransaction)

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=tx),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
            side_effect=PaymentAlreadyProcessedError(
                transaction_id="test_id", payment_status=PaymentStatus.PAID
            ),
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(),
        ) as mock_update,
    ):

        with pytest.raises(PaymentAlreadyProcessedError):
            await payment_service.webhook_confirm_transaction(
                data=data,
                session=mock_session,
            )

    mock_get.assert_awaited_once()
    mock_pending.assert_called_once_with(tx=tx)

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_transaction_success(
    payment_service,
    mock_session,
):
    transaction_id = uuid4()

    data = Mock()
    data.id = transaction_id

    tx = Mock(spec=PaymentTransaction)
    tx.status = PaymentStatus.PENDING
    tx.to_dict.return_value = {
        "id": str(transaction_id),
        "status": "CANCELED",
    }

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=tx),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
            return_value=None,
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(return_value=1),
        ) as mock_update,
        patch.object(
            mock_session,
            "refresh",
            new=AsyncMock(),
        ) as mock_refresh,
    ):

        result = await payment_service.cancel_transaction(
            session=mock_session,
            data=data,
        )

    mock_get.assert_awaited_once()
    mock_pending.assert_called_once_with(tx=tx)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs

    assert isinstance(call_kwargs["filters"], STransactionIDFilter)
    assert call_kwargs["filters"].id == transaction_id

    assert isinstance(call_kwargs["values"], SPaymentStatusCancel)
    assert call_kwargs["values"].status == PaymentStatus.CANCELED

    mock_refresh.assert_awaited_once_with(tx)

    assert result is not None


@pytest.mark.asyncio
async def test_cancel_transaction_not_found(
    payment_service,
    mock_session,
):
    data = Mock()
    data.id = uuid4()

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(
                side_effect=PaymentTransactionNotFoundError(
                    transaction_id="test_id", gateway_transaction_id="test_id"
                )
            ),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(),
        ) as mock_update,
    ):

        with pytest.raises(PaymentTransactionNotFoundError):
            await payment_service.cancel_transaction(
                session=mock_session,
                data=data,
            )

    mock_get.assert_awaited_once()
    mock_pending.assert_not_called()
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_transaction_not_pending(
    payment_service,
    mock_session,
):
    data = Mock()
    data.id = uuid4()

    tx = Mock(spec=PaymentTransaction)

    with (
        patch.object(
            payment_service,
            "_get_transaction_or_raise",
            new=AsyncMock(return_value=tx),
        ) as mock_get,
        patch.object(
            payment_service,
            "_ensure_pending",
            side_effect=PaymentAlreadyProcessedError(
                transaction_id="test_id", payment_status=PaymentStatus.CANCELED
            ),
        ) as mock_pending,
        patch.object(
            PaymentTransactionDAO,
            "update",
            new=AsyncMock(),
        ) as mock_update,
    ):

        with pytest.raises(PaymentAlreadyProcessedError):
            await payment_service.cancel_transaction(
                session=mock_session,
                data=data,
            )

    mock_get.assert_awaited_once()
    mock_pending.assert_called_once_with(tx=tx)

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_get_year_income_with_year(
    payment_service,
    mock_session,
):
    year = 2024
    dao_result = 123456

    with patch.object(
        PaymentTransactionDAO,
        "get_year_income",
        new=AsyncMock(return_value=dao_result),
    ) as mock_dao:

        result = await payment_service.get_year_income(
            session=mock_session,
            year=year,
        )

    mock_dao.assert_awaited_once_with(
        session=mock_session,
        year=year,
    )

    assert isinstance(result, SYearIncome)
    assert result.year_income == dao_result


@pytest.mark.asyncio
async def test_get_year_income_default_year(
    payment_service,
    mock_session,
):
    dao_result = 999

    with patch.object(
        PaymentTransactionDAO,
        "get_year_income",
        new=AsyncMock(return_value=dao_result),
    ) as mock_dao:

        result = await payment_service.get_year_income(
            session=mock_session,
            year=None,
        )

    mock_dao.assert_awaited_once_with(
        session=mock_session,
        year=None,
    )

    assert isinstance(result, SYearIncome)
    assert result.year_income == dao_result


class DummyTx:
    def __init__(self):
        self.id = uuid4()
        self.tg_id = 123
        self.user_id = 456
        self.subscription_months = 3
        self.is_premium = True
        self.is_founder = False
        self.description = None
        self.created_by_admin_id = None
        self.confirmed_by_admin_id = None
        self.gateway_transaction_id = "gw_123"
        self.confirmed_at = datetime.utcnow()
        self.paid_at = datetime.utcnow()
        self.amount = 1000
        self.currency = "RUB"
        self.status = PaymentStatus.PAID
        self.source = PaymentSource.GATEWAY


class DummyUser:
    def __init__(self):
        self.id = 1
        self.telegram_id = 123
        self.username = "test"
        self.first_name = "John"
        self.last_name = "Doe"
        self.has_used_trial = False
        self.role = SimpleNamespace(id=1, name="user", description="desc")
        self.subscriptions = []
        self.vpn_configs = []
        self.current_subscription = None


class DummyReferral:
    def __init__(self):
        self.success = True
        self.inviter_telegram_id = 999
        self.message = "ok"


@pytest.mark.asyncio
async def test_confirm_payment_flow_gateway_success(
    payment_service,
    mock_session,
):
    data = STransactionIDFilter(id=uuid4())

    tx = DummyTx()
    sub_res = DummyUser()
    referral = (True, 999)

    with (
        patch.object(
            payment_service,
            "webhook_confirm_transaction",
            new=AsyncMock(return_value=tx),
        ),
        patch.object(
            payment_service.sub_service,
            "activate_paid_subscription",
            new=AsyncMock(return_value=sub_res),
        ),
        patch.object(
            payment_service.ref_service,
            "grant_referral_bonus",
            new=AsyncMock(return_value=referral),
        ),
    ):

        result = await payment_service.confirm_payment_flow(
            session=mock_session,
            data=data,
            payment_source=PaymentSource.GATEWAY,
        )

    assert result.transaction_res.tg_id == 123
    assert result.subscription_res.id == 1
    assert result.referral_res.success is True
    assert result.referral_res.inviter_telegram_id == 999


@pytest.mark.asyncio
async def test_confirm_payment_flow_manual_success(
    payment_service,
    mock_session,
):
    data = SimpleNamespace(id=uuid4())

    tx = DummyTx()
    tx.tg_id = 111
    tx.subscription_months = 1
    tx.is_premium = False

    sub_res = DummyUser()

    referral_result = (False, None)

    with (
        patch.object(
            payment_service,
            "admin_confirm_transaction",
            new=AsyncMock(return_value=tx),
        ) as mock_confirm,
        patch.object(
            payment_service.sub_service,
            "activate_paid_subscription",
            new=AsyncMock(return_value=sub_res),
        ) as mock_sub,
        patch.object(
            payment_service.ref_service,
            "grant_referral_bonus",
            new=AsyncMock(return_value=referral_result),
        ) as mock_ref,
    ):

        result = await payment_service.confirm_payment_flow(
            session=mock_session,
            data=data,
            payment_source=PaymentSource.MANUAL,
            admin_id=1,
        )

    # --- asserts on orchestration ---
    mock_confirm.assert_awaited_once()
    mock_sub.assert_awaited_once()
    mock_ref.assert_awaited_once()

    # --- business assertions ---
    assert result.transaction_res.tg_id == 111
    assert result.subscription_res.id == 1
    assert result.subscription_res.telegram_id == 123
    assert result.referral_res.success is False
    assert result.referral_res.inviter_telegram_id is None


@pytest.mark.asyncio
async def test_confirm_payment_flow_referral_already_given(
    payment_service,
    mock_session,
):
    data = SimpleNamespace(id=uuid4())

    tx = DummyTx()
    sub_res = DummyUser()

    with (
        patch.object(
            payment_service,
            "webhook_confirm_transaction",
            new=AsyncMock(return_value=tx),
        ),
        patch.object(
            payment_service.sub_service,
            "activate_paid_subscription",
            new=AsyncMock(return_value=sub_res),
        ),
        patch.object(
            payment_service.ref_service,
            "grant_referral_bonus",
            new=AsyncMock(
                side_effect=ReferralBonusAlreadyGivenError(
                    invited_user_id=123, username="test_user"
                )
            ),
        ),
    ):

        result = await payment_service.confirm_payment_flow(
            session=mock_session,
            data=data,
            payment_source=PaymentSource.GATEWAY,
        )

    assert result.referral_res.success is False
    assert result.referral_res.inviter_telegram_id is None
    assert (
        result.referral_res.message
        == "Бонус за пользователя @test_user уже был начислен"
    )


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_confirm_payment_flow_manual_missing_admin(
    payment_service,
    mock_session,
):
    data = STransactionIDFilter(id=uuid4())

    with pytest.raises(ValueError):
        await payment_service.confirm_payment_flow(
            session=mock_session,
            data=data,
            payment_source=PaymentSource.MANUAL,
            admin_id=None,
        )
