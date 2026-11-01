from unittest.mock import patch

import pytest

from bot.expense.keyboards.inline_kb import (
    ExpenseAction,
    ExpenseCB,
    category_kb,
    confirm_kb,
    expense_menu_kb,
    expense_reminder_kb,
    node_kb,
    period_kb,
    skip_kb,
)
from shared.enums.expense_enum import ExpenseCategory


def _flatten_buttons(kb):
    """Возвращает плоский список кнопок из InlineKeyboardMarkup."""
    return [btn for row in kb.inline_keyboard for btn in row]


def test_expense_menu_kb_buttons():
    """expense_menu_kb содержит одну кнопку ADD."""
    kb = expense_menu_kb()
    buttons = _flatten_buttons(kb)
    assert len(buttons) == 1
    cb = ExpenseCB.unpack(buttons[0].callback_data)
    assert cb.action == ExpenseAction.ADD


def test_category_kb_has_all_categories():
    """category_kb содержит кнопку для каждой категории плюс кнопку Отмена."""
    kb = category_kb()
    buttons = _flatten_buttons(kb)
    # ExpenseCategory + кнопка «Отмена»
    assert len(buttons) == len(ExpenseCategory) + 1


def test_skip_kb_callback():
    """skip_kb содержит кнопку SKIP."""
    kb = skip_kb()
    buttons = _flatten_buttons(kb)
    skip_buttons = [
        b
        for b in buttons
        if ExpenseCB.unpack(b.callback_data).action == ExpenseAction.SKIP
    ]
    assert len(skip_buttons) == 1


def test_period_kb_callback():
    """period_kb содержит кнопку USE_CURRENT_PERIOD."""
    kb = period_kb()
    buttons = _flatten_buttons(kb)
    current_btns = [
        b
        for b in buttons
        if ExpenseCB.unpack(b.callback_data).action == ExpenseAction.USE_CURRENT_PERIOD
    ]
    assert len(current_btns) == 1


def test_node_kb_buttons():
    """node_kb содержит кнопки для каждой ноды + «Без привязки» + «Отмена»."""
    from bot.core.config import settings_bot

    kb = node_kb()
    buttons = _flatten_buttons(kb)
    # ноды + «Без привязки» + «Отмена»
    expected = len(settings_bot.vpn.nodes) + 2
    assert len(buttons) == expected


def test_confirm_kb_two_buttons():
    """confirm_kb содержит ровно две кнопки: CONFIRM и CANCEL."""
    kb = confirm_kb()
    buttons = _flatten_buttons(kb)
    assert len(buttons) == 2
    actions = {ExpenseCB.unpack(b.callback_data).action for b in buttons}
    assert ExpenseAction.CONFIRM in actions
    assert ExpenseAction.CANCEL in actions


def test_expense_reminder_kb_single_button():
    """expense_reminder_kb содержит одну кнопку MENU."""
    kb = expense_reminder_kb()
    buttons = _flatten_buttons(kb)
    assert len(buttons) == 1
    cb = ExpenseCB.unpack(buttons[0].callback_data)
    assert cb.action == ExpenseAction.MENU
