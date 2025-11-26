from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class UserPageCB(CallbackData, prefix="pagination_user"):  # type: ignore[misc,call-arg]
    pass


def common_user_buttons(
    builder: InlineKeyboardBuilder,
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> None:
    pass


def admin_user_control_kb(
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    pass


def role_selection_kb(
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    pass


def subscription_selection_kb(
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    pass


class AdminCB(CallbackData, prefix="admin"):  # type: ignore[misc,call-arg]
    pass


def admin_main_kb() -> InlineKeyboardMarkup:
    pass


def user_navigation_kb(
    filter_type: str,
    index: int,
    total: int,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    pass
