from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from bot.expense.adapter import ExpenseAPIAdapter
from bot.expense.schemas import SExpenseCreate, SExpenseRead, SYearlySummary
from bot.expense.services import ExpenseService
from shared.enums.expense_enum import ExpenseCategory


@pytest.fixture
def mock_adapter():
    """Мок ExpenseAPIAdapter."""
    return AsyncMock(spec=ExpenseAPIAdapter)


@pytest.fixture
def service(mock_adapter):
    """ExpenseService с мок-адаптером."""
    return ExpenseService(adapter=mock_adapter)


def _make_summary(year: int = 2026) -> SYearlySummary:
    return SYearlySummary(
        year=year,
        total_revenue=100000,
        total_expenses=50000,
        total_profit=50000,
        avg_check=500.0,
        arpu=1000.0,
        paying_users=100,
        total_users=200,
        conversion_pct=50.0,
    )


def _make_expense_read() -> SExpenseRead:
    return SExpenseRead(
        id=1,
        amount=5000,
        category=ExpenseCategory.SERVER,
        description=None,
        period_start=date(2026, 10, 1),
        period_end=None,
        node_name=None,
        is_recurring=True,
        created_at=datetime(2026, 10, 1),
        updated_at=datetime(2026, 10, 1),
    )


@pytest.mark.asyncio
async def test_get_yearly_summary_delegates(service, mock_adapter):
    """get_yearly_summary делегирует вызов адаптеру и возвращает его результат."""
    expected = _make_summary()
    mock_adapter.get_yearly_summary.return_value = expected

    result = await service.get_yearly_summary(year=2026)

    mock_adapter.get_yearly_summary.assert_awaited_once_with(year=2026)
    assert result is expected


@pytest.mark.asyncio
async def test_create_expense_delegates(service, mock_adapter):
    """create_expense делегирует вызов адаптеру и возвращает его результат."""
    payload = SExpenseCreate(
        amount=5000,
        category=ExpenseCategory.SERVER,
        period_start=date(2026, 10, 1),
    )
    expected = _make_expense_read()
    mock_adapter.create_expense.return_value = expected

    result = await service.create_expense(payload)

    mock_adapter.create_expense.assert_awaited_once_with(payload)
    assert result is expected
