"""Тесты для ExpenseRouter — FSM-хендлеры ввода расходов."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext

from bot.expense.router import ExpenseRouter, ExpenseStates
from bot.expense.schemas import SExpenseRead
from shared.enums.expense_enum import ExpenseCategory

# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot():
    """Мок бота Telegram."""
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot


@pytest.fixture
def mock_service():
    """Мок ExpenseService."""
    return AsyncMock()


@pytest.fixture
def router(mock_bot, mock_service):
    """ExpenseRouter с моками бота и сервиса."""
    with patch("bot.expense.router.settings_bot"):
        return ExpenseRouter(
            bot=mock_bot,
            logger=MagicMock(),
            expense_service=mock_service,
        )


@pytest.fixture
def mock_state():
    """Мок FSMContext."""
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={})
    return state


@pytest.fixture
def mock_callback():
    """Мок CallbackQuery с вложенным message."""
    query = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 123
    query.message = AsyncMock()
    query.message.message_id = 1
    query.message.chat = MagicMock()
    query.message.chat.id = 123
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    return query


@pytest.fixture
def mock_message():
    """Мок Message."""
    msg = AsyncMock()
    msg.chat = MagicMock()
    msg.chat.id = 123
    msg.from_user = MagicMock()
    msg.from_user.id = 123
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _make_expense_read(**kwargs) -> SExpenseRead:
    defaults = dict(
        id=1,
        amount=5000,
        category=ExpenseCategory.SERVER,
        description=None,
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        node_name=None,
        is_recurring=True,
        created_at=datetime(2026, 10, 1),
        updated_at=datetime(2026, 10, 1),
    )
    defaults.update(kwargs)
    return SExpenseRead(**defaults)


# ---------------------------------------------------------------------------
# Тесты expense_menu
# Декоратор @require_message извлекает msg из query.message — НЕ передаём msg явно
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_menu_shows_summary(router, mock_callback, mock_service):
    """expense_menu запрашивает summary и вызывает edit_text."""
    from bot.expense.schemas import SYearlySummary

    summary = SYearlySummary(
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
    mock_service.get_yearly_summary.return_value = summary

    with patch("bot.expense.router.ChatActionSender"):
        await router.expense_menu(
            query=mock_callback,
            callback_data=MagicMock(),
        )

    mock_service.get_yearly_summary.assert_awaited_once()
    mock_callback.message.edit_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Тесты start_add_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_add_expense_sets_state(router, mock_callback, mock_state):
    """start_add_expense устанавливает состояние select_category."""
    await router.start_add_expense(
        query=mock_callback,
        callback_data=MagicMock(),
        state=mock_state,
    )

    mock_state.set_state.assert_awaited()
    call_args = mock_state.set_state.call_args_list[0]
    assert call_args[0][0] == ExpenseStates.select_category
    mock_callback.message.edit_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Тесты category_selected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_selected_saves_and_asks_amount(
    router, mock_callback, mock_state
):
    """category_selected сохраняет категорию и переходит в enter_amount."""
    cb_data = MagicMock()
    cb_data.category = ExpenseCategory.SERVER

    await router.category_selected(
        query=mock_callback,
        callback_data=cb_data,
        state=mock_state,
    )

    mock_state.update_data.assert_awaited()
    update_kwargs = mock_state.update_data.call_args.kwargs
    assert update_kwargs.get("category") == ExpenseCategory.SERVER.value
    mock_state.set_state.assert_awaited_with(ExpenseStates.enter_amount)


# ---------------------------------------------------------------------------
# Тесты amount_entered (не имеет @require_message — передаём message напрямую)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_amount_entered_valid(router, mock_message, mock_state):
    """amount_entered: корректная сумма сохраняется, переходит в enter_description."""
    mock_message.text = "1500"
    mock_state.get_data.return_value = {"dialog_msg_id": 1, "category_label": "Сервер"}

    await router.amount_entered(message=mock_message, state=mock_state)

    mock_state.update_data.assert_awaited()
    update_kwargs = mock_state.update_data.call_args.kwargs
    assert update_kwargs.get("amount") == 1500
    mock_state.set_state.assert_awaited_with(ExpenseStates.enter_description)


@pytest.mark.asyncio
async def test_amount_entered_invalid(router, mock_message, mock_state):
    """amount_entered: невалидная сумма — состояние не меняется, показывается ошибка."""
    mock_message.text = "abc"
    mock_state.get_data.return_value = {
        "dialog_msg_id": None,
        "category_label": "Сервер",
    }

    await router.amount_entered(message=mock_message, state=mock_state)

    mock_state.set_state.assert_not_awaited()
    mock_message.delete.assert_awaited()


# ---------------------------------------------------------------------------
# Тесты skip_description
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_description_goes_to_period(router, mock_callback, mock_state):
    """skip_description сохраняет description=None, переходит в select_period."""
    await router.skip_description(
        query=mock_callback,
        callback_data=MagicMock(),
        state=mock_state,
    )

    mock_state.update_data.assert_awaited_with(description=None)
    mock_state.set_state.assert_awaited_with(ExpenseStates.select_period)


# ---------------------------------------------------------------------------
# Тесты description_entered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_description_entered_saves(router, mock_message, mock_state):
    """description_entered сохраняет описание и переходит в select_period."""
    mock_message.text = "Аренда сервера"
    mock_state.get_data.return_value = {"dialog_msg_id": None}

    await router.description_entered(message=mock_message, state=mock_state)

    mock_state.set_state.assert_awaited_with(ExpenseStates.select_period)
    update_calls = mock_state.update_data.call_args_list
    saved_desc = any(
        c.kwargs.get("description") == "Аренда сервера" for c in update_calls
    )
    assert saved_desc


# ---------------------------------------------------------------------------
# Тесты use_current_period
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_use_current_period(router, mock_callback, mock_state):
    """use_current_period вычисляет период текущего месяца, переходит в select_node."""
    await router.use_current_period(
        query=mock_callback,
        callback_data=MagicMock(),
        state=mock_state,
    )

    mock_state.set_state.assert_awaited_with(ExpenseStates.select_node)
    update_kwargs = mock_state.update_data.call_args.kwargs
    assert "period_start" in update_kwargs
    assert "period_end" in update_kwargs


# ---------------------------------------------------------------------------
# Тесты period_entered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_period_entered_valid(router, mock_message, mock_state):
    """period_entered: корректная дата — переходит в select_node с правильными датами."""
    mock_message.text = "2026-10-01"
    mock_state.get_data.return_value = {"dialog_msg_id": None}

    await router.period_entered(message=mock_message, state=mock_state)

    mock_state.set_state.assert_awaited_with(ExpenseStates.select_node)
    update_kwargs = mock_state.update_data.call_args.kwargs
    assert update_kwargs.get("period_start") == "2026-10-01"
    assert update_kwargs.get("period_end") == "2026-10-31"


@pytest.mark.asyncio
async def test_period_entered_invalid(router, mock_message, mock_state):
    """period_entered: некорректная дата — состояние не меняется."""
    mock_message.text = "not-a-date"
    mock_state.get_data.return_value = {"dialog_msg_id": None}

    await router.period_entered(message=mock_message, state=mock_state)

    mock_state.set_state.assert_not_awaited()
    mock_message.delete.assert_awaited()


# ---------------------------------------------------------------------------
# Тесты node_selected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_selected(router, mock_callback, mock_state):
    """node_selected сохраняет ноду, показывает подтверждение."""
    cb_data = MagicMock()
    cb_data.node_name = "fr-node"
    mock_state.get_data.return_value = {
        "category": "server",
        "amount": 5000,
        "description": None,
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
    }

    await router.node_selected(
        query=mock_callback,
        callback_data=cb_data,
        state=mock_state,
    )

    mock_state.set_state.assert_awaited_with(ExpenseStates.confirm)
    mock_callback.message.edit_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Тесты confirm_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_expense_calls_service(
    router, mock_callback, mock_service, mock_state
):
    """confirm_expense вызывает service.create_expense и очищает состояние."""
    mock_state.get_data.return_value = {
        "amount": 5000,
        "category": "server",
        "description": None,
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "node_name": None,
    }
    mock_service.create_expense.return_value = _make_expense_read()

    with patch("bot.expense.router.ChatActionSender"):
        await router.confirm_expense(
            query=mock_callback,
            callback_data=MagicMock(),
            state=mock_state,
        )

    mock_service.create_expense.assert_awaited_once()
    mock_state.clear.assert_awaited_once()
    mock_callback.message.edit_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Тесты cancel_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_expense_clears_state(router, mock_callback, mock_state):
    """cancel_expense очищает состояние и отвечает toast-ом."""
    await router.cancel_expense(
        query=mock_callback,
        callback_data=MagicMock(),
        state=mock_state,
    )

    mock_state.clear.assert_awaited_once()
    mock_callback.answer.assert_awaited_once()
    mock_callback.message.edit_text.assert_awaited_once()
