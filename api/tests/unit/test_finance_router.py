"""Тесты для api/finance/router.py — 4 GET-эндпоинта."""

from unittest.mock import AsyncMock

import pytest

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.finance.dependencies import get_finance_service
from api.finance.schemas import (
    SBreakevenInfo,
    SMonthlyPnL,
    SMonthlyTrend,
    SYearlySummary,
)
from api.tests.conftest import fake_admin


@pytest.fixture
def mock_finance_service():
    """Мок FinanceService."""
    return AsyncMock()


@pytest.fixture
def client(make_client, mock_finance_service, mock_session):
    """TestClient с подменёнными зависимостями."""
    with make_client(
        {
            get_finance_service: lambda: mock_finance_service,
            get_session: lambda: mock_session,
            check_admin_role: lambda: fake_admin(),
        }
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /finance/pnl
# ---------------------------------------------------------------------------


def test_get_pnl_200(client, mock_finance_service):
    """GET /finance/pnl?year=2026 → 200, список P&L."""
    mock_finance_service.get_monthly_pnl.return_value = [
        SMonthlyPnL(
            month="2026-10", revenue=10000, expenses=3000, profit=7000, margin_pct=70.0
        )
    ]

    resp = client.get("/finance/pnl", params={"year": 2026})

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    mock_finance_service.get_monthly_pnl.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /finance/summary
# ---------------------------------------------------------------------------


def test_get_summary_200(client, mock_finance_service):
    """GET /finance/summary?year=2026 → 200."""
    mock_finance_service.get_yearly_summary.return_value = SYearlySummary(
        year=2026,
        total_revenue=100000,
        total_expenses=50000,
        total_profit=50000,
        avg_check=500.0,
        arpu=1000.0,
        paying_users=100,
        total_users=200,
        conversion_pct=50.0,
    )

    resp = client.get("/finance/summary", params={"year": 2026})

    assert resp.status_code == 200
    assert resp.json()["year"] == 2026


# ---------------------------------------------------------------------------
# GET /finance/breakeven
# ---------------------------------------------------------------------------


def test_get_breakeven_200(client, mock_finance_service):
    """GET /finance/breakeven → 200."""
    mock_finance_service.get_breakeven.return_value = SBreakevenInfo(
        monthly_expenses=10000,
        avg_check=500.0,
        payments_needed=20,
        current_monthly_payments=15,
        gap=5,
    )

    resp = client.get("/finance/breakeven")

    assert resp.status_code == 200
    assert resp.json()["payments_needed"] == 20


# ---------------------------------------------------------------------------
# GET /finance/trend
# ---------------------------------------------------------------------------


def test_get_trend_200(client, mock_finance_service):
    """GET /finance/trend?months=6 → 200."""
    mock_finance_service.get_trend.return_value = [
        SMonthlyTrend(month="2026-10", revenue=10000, mom_pct=None),
        SMonthlyTrend(month="2026-11", revenue=12000, mom_pct=20.0),
    ]

    resp = client.get("/finance/trend", params={"months": 6})

    assert resp.status_code == 200
    assert len(resp.json()) == 2
