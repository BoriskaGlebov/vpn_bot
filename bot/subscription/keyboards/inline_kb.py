from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup


class SubscriptionCB(CallbackData, prefix="sub"):  # type: ignore[misc,call-arg]
    pass


class ToggleSubscriptionCB(CallbackData, prefix="toggle_sub"):  # type: ignore[misc,call-arg]
    pass


class AdminPaymentCB(CallbackData, prefix="admin"):  # type: ignore[misc,call-arg]
    pass


def subscription_options_kb(
    premium: bool = False, trial: bool = False
) -> InlineKeyboardMarkup:
    pass


def payment_confirm_kb(months: int) -> InlineKeyboardMarkup:
    pass


def admin_payment_kb(user_id: int, months: int, premium: bool) -> InlineKeyboardMarkup:
    pass
