from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from api.payment.dao import PaymentTransactionDAO


@pytest.mark.asyncio
async def test_get_year_income(mock_session):
    """Суммирует доход за явно переданный год."""
    expected_income = 15000

    result_mock = Mock()
    result_mock.scalar_one.return_value = expected_income

    mock_session.execute = AsyncMock(return_value=result_mock)

    income = await PaymentTransactionDAO.get_year_income(
        session=mock_session,
        year=2025,
    )

    assert income == expected_income
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_year_income_current_year(mocker, mock_session):
    """Год не передан -> DAO подставляет текущий год (UTC now)."""
    mocked_now = datetime(2026, 5, 10, tzinfo=UTC)

    datetime_mock = Mock()
    datetime_mock.now.return_value = mocked_now
    datetime_mock.side_effect = datetime

    mocker.patch(
        "api.payment.dao.datetime",
        datetime_mock,
    )

    result_mock = Mock()
    result_mock.scalar_one.return_value = 5000

    mock_session.execute.return_value = result_mock

    income = await PaymentTransactionDAO.get_year_income(
        session=mock_session,
    )

    assert income == 5000
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_year_income_builds_query(mock_session):
    """Собранный SQL реально суммирует amount и фильтрует по paid_at (не просто заглушка)."""
    result_mock = Mock()()
    result_mock.scalar_one.return_value = 100

    mock_session.execute.return_value = result_mock

    await PaymentTransactionDAO.get_year_income(
        session=mock_session,
        year=2025,
    )

    stmt = mock_session.execute.await_args.args[0]

    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "sum(" in compiled.lower()
    assert "amount" in compiled.lower()
    assert "paid_at" in compiled.lower()
