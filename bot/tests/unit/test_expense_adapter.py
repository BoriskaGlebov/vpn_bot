from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from bot.expense.adapter import ExpenseAPIAdapter
from bot.expense.schemas import SExpenseCreate, SExpenseRead, SYearlySummary
from shared.enums.expense_enum import ExpenseCategory


@pytest.fixture
def mock_client():
    """Мок APIClient."""
    return AsyncMock()


@pytest.fixture
def adapter(mock_client):
    """Адаптер с мок-клиентом."""
    return ExpenseAPIAdapter(client=mock_client)


def _yearly_summary_dict(year: int = 2026) -> dict:
    return {
        "year": year,
        "total_revenue": 100000,
        "total_expenses": 50000,
        "total_profit": 50000,
        "avg_check": 500.0,
        "arpu": 1000.0,
        "paying_users": 100,
        "total_users": 200,
        "conversion_pct": 50.0,
    }


@pytest.mark.asyncio
async def test_get_yearly_summary_success(adapter, mock_client):
    """get_yearly_summary возвращает SYearlySummary при успешном ответе."""
    mock_client.get.return_value = (_yearly_summary_dict(2026), 200)

    result = await adapter.get_yearly_summary(year=2026)

    assert isinstance(result, SYearlySummary)
    assert result.year == 2026
    assert result.total_revenue == 100000
    mock_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_yearly_summary_default_year(adapter, mock_client):
    """Если year=None, клиент вызывается с текущим годом."""
    current_year = datetime.now().year
    mock_client.get.return_value = (_yearly_summary_dict(current_year), 200)

    await adapter.get_yearly_summary()

    call_kwargs = mock_client.get.call_args
    assert call_kwargs is not None
    params = (
        call_kwargs.kwargs.get("params") or call_kwargs.args[1]
        if len(call_kwargs.args) > 1
        else call_kwargs.kwargs.get("params")
    )
    # Проверяем, что year передан в params и равен текущему году
    assert params is not None
    assert params.get("year") == current_year


@pytest.mark.asyncio
async def test_create_expense_success(adapter, mock_client):
    """create_expense возвращает SExpenseRead при успешном ответе."""
    payload = SExpenseCreate(
        amount=5000,
        category=ExpenseCategory.SERVER,
        period_start=date(2026, 10, 1),
    )
    response_data = {
        "id": 1,
        "amount": 5000,
        "category": "server",
        "description": None,
        "period_start": "2026-10-01",
        "period_end": None,
        "node_name": None,
        "is_recurring": True,
        "created_at": "2026-10-01T12:00:00",
        "updated_at": "2026-10-01T12:00:00",
    }
    mock_client.post.return_value = (response_data, 201)

    result = await adapter.create_expense(payload)

    assert isinstance(result, SExpenseRead)
    assert result.id == 1
    assert result.amount == 5000
    mock_client.post.assert_awaited_once()
