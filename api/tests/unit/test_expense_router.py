"""Тесты для api/expense/router.py — 6 эндпоинтов."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.expense.dependencies import get_expense_service
from api.tests.conftest import fake_admin
from shared.enums.expense_enum import ExpenseCategory


@pytest.fixture
def mock_expense_service():
    """Мок ExpenseService."""
    return AsyncMock()


@pytest.fixture
def client(make_client, mock_expense_service, mock_session):
    """TestClient с подменёнными зависимостями."""
    with make_client(
        {
            get_expense_service: lambda: mock_expense_service,
            get_session: lambda: mock_session,
            check_admin_role: lambda: fake_admin(),
        }
    ) as c:
        yield c


def _fake_expense(**kwargs):
    defaults = dict(
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
    defaults.update(kwargs)
    obj = MagicMock(**defaults)
    obj.category = ExpenseCategory.SERVER
    return obj


# ---------------------------------------------------------------------------
# POST /expenses → 201
# ---------------------------------------------------------------------------


def test_create_expense_201(client, mock_expense_service):
    """POST /expenses возвращает 201 с созданной записью."""
    mock_expense_service.create.return_value = _fake_expense()

    resp = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "category": "server",
            "period_start": "2026-10-01",
        },
    )

    assert resp.status_code == 201
    assert resp.json()["id"] == 1


# ---------------------------------------------------------------------------
# GET /expenses/summary → 200
# ---------------------------------------------------------------------------


def test_get_expense_summary_200(client, mock_expense_service):
    """GET /expenses/summary возвращает 200."""
    from api.expense.schemas import SMonthlyExpenseSummary

    mock_expense_service.get_monthly_summary.return_value = [
        SMonthlyExpenseSummary(month="2026-10", total=5000)
    ]

    resp = client.get("/expenses/summary", params={"year": 2026})

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# GET /expenses → 200
# ---------------------------------------------------------------------------


def test_get_expenses_200(client, mock_expense_service):
    """GET /expenses возвращает 200 со списком записей."""
    mock_expense_service.get_all.return_value = [_fake_expense()]

    resp = client.get("/expenses")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# GET /expenses/{id} → 200
# ---------------------------------------------------------------------------


def test_get_expense_by_id_200(client, mock_expense_service):
    """GET /expenses/1 возвращает 200."""
    mock_expense_service.get_by_id.return_value = _fake_expense(id=1)

    resp = client.get("/expenses/1")

    assert resp.status_code == 200
    assert resp.json()["id"] == 1


# ---------------------------------------------------------------------------
# PATCH /expenses/{id} → 200
# ---------------------------------------------------------------------------


def test_update_expense_200(client, mock_expense_service):
    """PATCH /expenses/1 возвращает 200 с обновлённой записью."""
    mock_expense_service.update.return_value = _fake_expense(amount=9999)

    resp = client.patch("/expenses/1", json={"amount": 9999})

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /expenses/{id} → 204
# ---------------------------------------------------------------------------


def test_delete_expense_204(client, mock_expense_service):
    """DELETE /expenses/1 возвращает 204."""
    mock_expense_service.delete.return_value = None

    resp = client.delete("/expenses/1")

    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# GET /expenses/999 → 404
# ---------------------------------------------------------------------------


def test_get_expense_not_found(client, mock_expense_service):
    """GET /expenses/999 возвращает 404, если сервис бросает ExpenseNotFoundError."""
    from api.app_error.base_error import ExpenseNotFoundError

    mock_expense_service.get_by_id.side_effect = ExpenseNotFoundError(expense_id=999)

    resp = client.get("/expenses/999")

    assert resp.status_code == 404
