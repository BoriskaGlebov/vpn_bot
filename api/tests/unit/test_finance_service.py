"""Тесты для api/finance/services.py — FinanceService (4 метода)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.finance.services import FinanceService


@pytest.fixture
def service():
    """Экземпляр FinanceService."""
    return FinanceService()


# ---------------------------------------------------------------------------
# get_monthly_pnl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_monthly_pnl_merges_revenue_and_expenses(service, mock_session):
    """P&L за октябрь: revenue=10000, expenses=3000 → profit=7000."""
    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.ExpenseDAO") as exp_dao,
    ):
        pay_dao.get_monthly_revenue = AsyncMock(return_value=[("2026-10", 10000)])
        exp_dao.get_monthly_totals = AsyncMock(return_value=[("2026-10", 3000)])

        result = await service.get_monthly_pnl(session=mock_session, year=2026)

    assert len(result) == 1
    assert result[0].month == "2026-10"
    assert result[0].revenue == 10000
    assert result[0].expenses == 3000
    assert result[0].profit == 7000


@pytest.mark.asyncio
async def test_get_monthly_pnl_different_months(service, mock_session):
    """Revenue за октябрь и expenses за ноябрь — два отдельных P&L."""
    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.ExpenseDAO") as exp_dao,
    ):
        pay_dao.get_monthly_revenue = AsyncMock(return_value=[("2026-10", 10000)])
        exp_dao.get_monthly_totals = AsyncMock(return_value=[("2026-11", 3000)])

        result = await service.get_monthly_pnl(session=mock_session, year=2026)

    months = {r.month for r in result}
    assert "2026-10" in months
    assert "2026-11" in months
    assert len(result) == 2


# ---------------------------------------------------------------------------
# get_yearly_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_yearly_summary_calculates_metrics(service, mock_session):
    """Годовой итог: avg_check, arpu и conversion вычисляются правильно."""
    count_result = MagicMock()
    count_result.scalar_one.return_value = 200
    mock_session.execute = AsyncMock(return_value=count_result)

    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.ExpenseDAO") as exp_dao,
    ):
        pay_dao.get_year_income = AsyncMock(return_value=100000)
        exp_dao.get_monthly_totals = AsyncMock(return_value=[("2026-10", 30000)])
        pay_dao.count_paying_users = AsyncMock(return_value=50)
        pay_dao.count_paid_transactions = AsyncMock(return_value=200)

        result = await service.get_yearly_summary(session=mock_session, year=2026)

    assert result.avg_check == round(100000 / 200, 2)
    assert result.arpu == round(100000 / 50, 2)
    assert result.conversion_pct == round(50 / 200 * 100, 2)


@pytest.mark.asyncio
async def test_get_yearly_summary_zero_division(service, mock_session):
    """Нулевые paying_users и total_users не вызывают ZeroDivisionError."""
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    mock_session.execute = AsyncMock(return_value=count_result)

    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.ExpenseDAO") as exp_dao,
    ):
        pay_dao.get_year_income = AsyncMock(return_value=0)
        exp_dao.get_monthly_totals = AsyncMock(return_value=[])
        pay_dao.count_paying_users = AsyncMock(return_value=0)
        pay_dao.count_paid_transactions = AsyncMock(return_value=0)

        result = await service.get_yearly_summary(session=mock_session, year=2026)

    assert result.avg_check == 0.0
    assert result.arpu == 0.0
    assert result.conversion_pct == 0.0


# ---------------------------------------------------------------------------
# get_breakeven
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_breakeven(service, mock_session):
    """Точка безубыточности: payments_needed = ceil(monthly_expenses / avg_check)."""
    import math

    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.ExpenseDAO") as exp_dao,
        patch("api.finance.services.datetime") as mock_dt,
    ):
        from datetime import timezone

        mock_dt.now.return_value = MagicMock(year=2026, month=10)
        exp_dao.get_monthly_totals = AsyncMock(return_value=[("2026-10", 30000)])
        pay_dao.get_year_income = AsyncMock(return_value=100000)
        pay_dao.count_paid_transactions = AsyncMock(return_value=200)
        pay_dao.count_monthly_payments = AsyncMock(return_value=15)

        result = await service.get_breakeven(session=mock_session)

    monthly_expenses = 30000 // 10
    avg_check = round(100000 / 200, 2)
    expected_needed = math.ceil(monthly_expenses / avg_check)
    assert result.payments_needed == expected_needed
    assert result.current_monthly_payments == 15


@pytest.mark.asyncio
async def test_get_breakeven_zero_avg_check(service, mock_session):
    """При avg_check=0 payments_needed=0, без деления на ноль."""
    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.ExpenseDAO") as exp_dao,
        patch("api.finance.services.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = MagicMock(year=2026, month=10)
        exp_dao.get_monthly_totals = AsyncMock(return_value=[])
        pay_dao.get_year_income = AsyncMock(return_value=0)
        pay_dao.count_paid_transactions = AsyncMock(return_value=0)
        pay_dao.count_monthly_payments = AsyncMock(return_value=0)

        result = await service.get_breakeven(session=mock_session)

    assert result.payments_needed == 0


# ---------------------------------------------------------------------------
# get_trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trend_mom_calculation(service, mock_session):
    """MoM за два месяца: 100 → 120 → mom_pct = 20.0."""
    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = MagicMock(year=2026, month=11)
        pay_dao.get_monthly_revenue = AsyncMock(
            return_value=[("2026-10", 100), ("2026-11", 120)]
        )

        result = await service.get_trend(session=mock_session, months=2)

    nov = next((r for r in result if r.month == "2026-11"), None)
    assert nov is not None
    assert nov.mom_pct == 20.0


@pytest.mark.asyncio
async def test_get_trend_first_month_none(service, mock_session):
    """Первый месяц тренда имеет mom_pct=None."""
    with (
        patch("api.finance.services.PaymentTransactionDAO") as pay_dao,
        patch("api.finance.services.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = MagicMock(year=2026, month=11)
        pay_dao.get_monthly_revenue = AsyncMock(
            return_value=[("2026-10", 100), ("2026-11", 120)]
        )

        result = await service.get_trend(session=mock_session, months=2)

    # Первый из возвращённых элементов — октябрь (самый ранний из N)
    # У первого элемента mom_pct=None, так как нет предыдущего месяца в выборке
    first = result[0]
    assert first.mom_pct is None
