from typing import Tuple

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def subscription_options_kb() -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру с вариантами подписки для пользователя.

    Варианты подписки включают месяцы и бесплатный 14-дневный период.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура с кнопками подписки и кнопкой отмены.

    """
    builder = InlineKeyboardBuilder()
    options: list[Tuple[str, int]] = [
        ("1 месяц — 70₽", 1),
        ("3 месяца — 160₽", 3),
        ("6 месяцев — 300₽", 6),
        ("12 месяцев — 600₽", 12),
        ("14 дней - Бесплатно", 14),
    ]
    for label, months in options:
        builder.button(text=f"📆 {label}", callback_data=f"sub_select:{months}")
    builder.button(text="❌ Отмена", callback_data="sub_cancel")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def payment_confirm_kb(months: int) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для подтверждения оплаты пользователем.

    Args
        months (int): Количество месяцев подписки, за которые пользователь произвёл оплату.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура с кнопками "Я оплатил" и "Отмена".

    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я оплатил", callback_data=f"sub_paid:{months}")
    builder.button(text="❌ Отмена", callback_data="sub_cancel")
    return builder.as_markup()


def admin_payment_kb(user_id: int, months: int) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для администраторов для подтверждения или отклонения оплаты пользователя.

    Args
        user_id (int): Идентификатор пользователя, для которого администратор подтверждает оплату.
        months (int): Количество месяцев подписки, за которые пользователь произвёл оплату.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура с кнопками "Подтвердить" и "Отменить".

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить", callback_data=f"admin_confirm:{user_id}:{months}"
    )
    builder.button(
        text="❌ Отменить", callback_data=f"admin_decline:{user_id}:{months}"
    )
    return builder.as_markup()
