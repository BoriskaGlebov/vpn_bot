"""Тесты для api/expense/services.py — ExpenseService."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.app_error.base_error import ExpenseNotFoundError, InvalidNodeNameError
from api.expense.schemas import SExpenseCreate, SExpenseFilter, SExpenseUpdate
from api.expense.services import ExpenseService
from shared.enums.expense_enum import ExpenseCategory


@pytest.fixture
def service():
    """Экземпляр ExpenseService."""
    return ExpenseService()


def _make_fake_expense(**kwargs):
    defaults = dict(
        id=1,
        amount=5000,
        category=ExpenseCategory.SERVER,
        description=None,
        period_start=date(2026, 10, 1),
        period_end=None,
        node_name=None,
        is_recurring=True,
    )
    defaults.update(kwargs)
    return MagicMock(**defaults)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_calls_dao_add(service, mock_session):
    """create вызывает ExpenseDAO.add и возвращает созданную запись."""
    payload = SExpenseCreate(
        amount=1000,
        category=ExpenseCategory.SERVER,
        period_start=date(2026, 10, 1),
    )
    fake_expense = _make_fake_expense(id=1)

    with patch("api.expense.services.ExpenseDAO") as dao_mock:
        dao_mock.add = AsyncMock(return_value=fake_expense)
        result = await service.create(session=mock_session, data=payload)

    assert result.id == 1
    dao_mock.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_validates_node_name(service, mock_session):
    """create бросает InvalidNodeNameError при несуществующей ноде."""
    payload = SExpenseCreate(
        amount=1000,
        category=ExpenseCategory.SERVER,
        period_start=date(2026, 10, 1),
        node_name="nonexistent-node",
    )

    with patch("api.expense.services.settings_api") as mock_settings:
        mock_settings.vpn_node_names = frozenset({"fr-node", "de-node"})
        with pytest.raises(InvalidNodeNameError):
            await service.create(session=mock_session, data=payload)


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_id_found(service, mock_session):
    """get_by_id возвращает запись, если она существует."""
    fake_expense = _make_fake_expense(id=5)

    with patch("api.expense.services.ExpenseDAO") as dao_mock:
        dao_mock.find_one_or_none_by_id = AsyncMock(return_value=fake_expense)
        result = await service.get_by_id(session=mock_session, expense_id=5)

    assert result is fake_expense


@pytest.mark.asyncio
async def test_get_by_id_not_found(service, mock_session):
    """get_by_id бросает ExpenseNotFoundError, если запись не найдена."""
    with patch("api.expense.services.ExpenseDAO") as dao_mock:
        dao_mock.find_one_or_none_by_id = AsyncMock(return_value=None)
        with pytest.raises(ExpenseNotFoundError):
            await service.get_by_id(session=mock_session, expense_id=999)


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_delegates(service, mock_session):
    """get_all делегирует вызов ExpenseDAO.find_all с переданными фильтрами."""
    filters = SExpenseFilter(category=ExpenseCategory.SERVER)
    fake_list = [_make_fake_expense()]

    with patch("api.expense.services.ExpenseDAO") as dao_mock:
        dao_mock.find_all = AsyncMock(return_value=fake_list)
        result = await service.get_all(session=mock_session, filters=filters)

    dao_mock.find_all.assert_awaited_once_with(session=mock_session, filters=filters)
    assert result is fake_list


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_found(service, mock_session):
    """update вызывает get_by_id + ExpenseDAO.patch."""
    fake_expense = _make_fake_expense(id=1)
    updated_expense = _make_fake_expense(id=1, amount=9999)
    data = SExpenseUpdate(amount=9999)

    with (
        patch("api.expense.services.ExpenseDAO") as dao_mock,
        patch.object(service, "get_by_id", new=AsyncMock(return_value=fake_expense)),
    ):
        dao_mock.patch = AsyncMock(return_value=updated_expense)
        result = await service.update(session=mock_session, expense_id=1, data=data)

    dao_mock.patch.assert_awaited_once()
    assert result is updated_expense


@pytest.mark.asyncio
async def test_update_not_found(service, mock_session):
    """update бросает ExpenseNotFoundError, если запись не найдена."""
    data = SExpenseUpdate(amount=9999)

    with patch.object(
        service,
        "get_by_id",
        new=AsyncMock(side_effect=ExpenseNotFoundError(expense_id=999)),
    ):
        with pytest.raises(ExpenseNotFoundError):
            await service.update(session=mock_session, expense_id=999, data=data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_found(service, mock_session):
    """delete вызывает get_by_id и ExpenseDAO.delete."""
    fake_expense = _make_fake_expense(id=1)

    with (
        patch("api.expense.services.ExpenseDAO") as dao_mock,
        patch.object(service, "get_by_id", new=AsyncMock(return_value=fake_expense)),
    ):
        dao_mock.delete = AsyncMock()
        await service.delete(session=mock_session, expense_id=1)

    dao_mock.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_not_found(service, mock_session):
    """delete бросает ExpenseNotFoundError, если запись не найдена."""
    with patch.object(
        service,
        "get_by_id",
        new=AsyncMock(side_effect=ExpenseNotFoundError(expense_id=999)),
    ):
        with pytest.raises(ExpenseNotFoundError):
            await service.delete(session=mock_session, expense_id=999)


# ---------------------------------------------------------------------------
# get_monthly_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_monthly_summary(service, mock_session):
    """get_monthly_summary преобразует DAO-строки в SMonthlyExpenseSummary."""
    rows = [("2026-10", 5000), ("2026-11", 3000)]

    with patch("api.expense.services.ExpenseDAO") as dao_mock:
        dao_mock.get_monthly_totals = AsyncMock(return_value=rows)
        result = await service.get_monthly_summary(session=mock_session, year=2026)

    assert len(result) == 2
    assert result[0].month == "2026-10"
    assert result[0].total == 5000
