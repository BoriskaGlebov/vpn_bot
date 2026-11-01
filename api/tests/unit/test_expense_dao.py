"""Тесты для api/expense/dao.py — 3 метода: get_by_period, get_monthly_totals, get_yearly_by_category."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.expense.dao import ExpenseDAO


@pytest.mark.asyncio
async def test_get_by_period_returns_list(mock_session):
    """get_by_period возвращает список расходов из session.execute."""
    fake_expense = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [fake_expense]
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await ExpenseDAO.get_by_period(
        session=mock_session,
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
    )

    assert result == [fake_expense]
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_monthly_totals_returns_tuples(mock_session):
    """get_monthly_totals возвращает список кортежей (month, total)."""
    row1 = MagicMock()
    row1.month = "2026-10"
    row1.total = 5000
    result_mock = MagicMock()
    result_mock.all.return_value = [row1]
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await ExpenseDAO.get_monthly_totals(session=mock_session, year=2026)

    assert len(result) == 1
    assert result[0] == ("2026-10", 5000)
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_yearly_by_category_returns_tuples(mock_session):
    """get_yearly_by_category возвращает список кортежей (category, total)."""
    from shared.enums.expense_enum import ExpenseCategory

    row1 = MagicMock()
    row1.__getitem__ = lambda self, idx: [ExpenseCategory.SERVER, 15000][idx]
    result_mock = MagicMock()
    result_mock.all.return_value = [row1]
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await ExpenseDAO.get_yearly_by_category(session=mock_session, year=2026)

    assert len(result) == 1
    assert result[0][0] == "server"
    assert result[0][1] == 15000
    mock_session.execute.assert_awaited_once()
