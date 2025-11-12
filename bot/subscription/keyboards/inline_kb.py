from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import settings_bot


def subscription_options_kb() -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру с вариантами подписки для пользователя.

    Варианты подписки включают месяцы и бесплатный 14-дневный период.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура с кнопками подписки и кнопкой отмены.

    """
    price_map = settings_bot.PRICE_MAP
    builder = InlineKeyboardBuilder()
    options: list[tuple[str, int]] = [
        (f"1 месяц — {price_map[1]}₽", 1),
        (f"3 месяца — {price_map[3]}₽", 3),
        (f"6 месяцев — {price_map[6]}₽", 6),
        (f"12 месяцев — {price_map[12]}₽", 12),
        ("7 дней - Бесплатно", 7),
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
