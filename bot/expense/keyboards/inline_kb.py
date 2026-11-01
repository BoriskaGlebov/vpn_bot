from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.core.config import settings_bot
from shared.enums.expense_enum import ExpenseCategory


class ExpenseAction(StrEnum):
    """Действия в меню расходов."""

    MENU = "menu"
    ADD = "add"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    SKIP = "skip"
    USE_CURRENT_PERIOD = "use_current"


class ExpenseCB(CallbackData, prefix="expense"):  # type: ignore[misc,call-arg]
    """Callback для общих действий с расходами."""

    action: ExpenseAction


class ExpenseCategoryCB(CallbackData, prefix="exp_cat"):  # type: ignore[misc,call-arg]
    """Callback для выбора категории расхода."""

    category: ExpenseCategory


class ExpenseNodeCB(CallbackData, prefix="exp_node"):  # type: ignore[misc,call-arg]
    """Callback для выбора ноды."""

    node_name: str


CATEGORY_LABELS: dict[ExpenseCategory, str] = {
    ExpenseCategory.SERVER: "🖥 Сервер",
    ExpenseCategory.DOMAIN: "🌐 Домен",
    ExpenseCategory.IP_ADDRESS: "🔢 IP-адрес",
    ExpenseCategory.AI_LLM: "🤖 AI/LLM",
    ExpenseCategory.ADVERTISING: "📣 Реклама",
    ExpenseCategory.OTHER: "📦 Прочее",
}


def expense_menu_kb() -> InlineKeyboardMarkup:
    """Меню расходов: кнопка «Добавить расход».

    Returns
        InlineKeyboardMarkup: Клавиатура меню расходов.

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Добавить расход",
        callback_data=ExpenseCB(action=ExpenseAction.ADD),
    )
    builder.adjust(1)
    return builder.as_markup()


def category_kb() -> InlineKeyboardMarkup:
    """Выбор категории расхода.

    Returns
        InlineKeyboardMarkup: Клавиатура выбора категории.

    """
    builder = InlineKeyboardBuilder()
    for cat, label in CATEGORY_LABELS.items():
        builder.button(
            text=label,
            callback_data=ExpenseCategoryCB(category=cat),
        )
    builder.button(
        text="❌ Отмена",
        callback_data=ExpenseCB(action=ExpenseAction.CANCEL),
    )
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def skip_kb() -> InlineKeyboardMarkup:
    """Кнопка «Пропустить» (для описания).

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопкой пропуска.

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⏩ Пропустить",
        callback_data=ExpenseCB(action=ExpenseAction.SKIP),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=ExpenseCB(action=ExpenseAction.CANCEL),
    )
    builder.adjust(1)
    return builder.as_markup()


def period_kb() -> InlineKeyboardMarkup:
    """Выбор периода: текущий месяц или ввести вручную.

    Returns
        InlineKeyboardMarkup: Клавиатура выбора периода.

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📅 Текущий месяц",
        callback_data=ExpenseCB(action=ExpenseAction.USE_CURRENT_PERIOD),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=ExpenseCB(action=ExpenseAction.CANCEL),
    )
    builder.adjust(1)
    return builder.as_markup()


def node_kb() -> InlineKeyboardMarkup:
    """Выбор ноды (из конфига) + «Без привязки».

    Returns
        InlineKeyboardMarkup: Клавиатура выбора VPN-ноды.

    """
    builder = InlineKeyboardBuilder()
    for name in sorted(settings_bot.vpn.nodes.keys()):
        builder.button(
            text=name,
            callback_data=ExpenseNodeCB(node_name=name),
        )
    builder.button(
        text="🚫 Без привязки",
        callback_data=ExpenseNodeCB(node_name=""),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=ExpenseCB(action=ExpenseAction.CANCEL),
    )
    cols = 2
    node_count = len(settings_bot.vpn.nodes)
    rows = [cols] * (node_count // cols)
    if node_count % cols:
        rows.append(node_count % cols)
    rows.extend([1, 1])
    builder.adjust(*rows)
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    """Подтверждение создания расхода.

    Returns
        InlineKeyboardMarkup: Клавиатура подтверждения.

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=ExpenseCB(action=ExpenseAction.CONFIRM),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=ExpenseCB(action=ExpenseAction.CANCEL),
    )
    builder.adjust(2)
    return builder.as_markup()
