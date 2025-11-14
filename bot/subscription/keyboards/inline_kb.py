from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings_bot


def subscription_options_kb(
    premium: bool = False, trial: bool = False
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру с вариантами подписки.

    Пользователь может выбрать обычную или премиум-подписку.
    В премиум-режиме цены удваиваются, а описание опций обновляется.

    Args:
        premium (bool): Флаг премиум-режима (по умолчанию False).
        trial (bool): Пробный период, отключена если уже есть активная подписка

    Returns
        InlineKeyboardMarkup: Клавиатура с вариантами подписки.

    """
    price_map = settings_bot.PRICE_MAP
    builder = InlineKeyboardBuilder()

    multiplier = 2 if premium else 1
    label_prefix = "⭐" if premium else "📆"

    options: list[tuple[str, int]] = [
        (f"1 месяц — {price_map[1] * multiplier}₽", 1),
        (f"3 месяца — {price_map[3] * multiplier}₽", 3),
        (f"6 месяцев — {price_map[6] * multiplier}₽", 6),
        (f"12 месяцев — {price_map[12] * multiplier}₽", 12),
    ]

    for label, months in options:
        builder.button(
            text=f"{label_prefix} {label}", callback_data=f"sub_select:{months}"
        )

    # добавляем кнопку "Бесплатно" только для обычного режима
    if not premium and trial:
        builder.button(text="🎁 7 дней — Бесплатно", callback_data="sub_select:7")

    # кнопка переключения режима
    if premium:
        builder.button(
            text="⬅️ Вернуться к стандартной подписке",
            callback_data="sub_toggle:standard",
        )
    else:
        builder.button(text="🌟 Перейти в Премиум", callback_data="sub_toggle:premium")

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


def admin_payment_kb(user_id: int, months: int, premium: bool) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для администраторов для подтверждения или отклонения оплаты пользователя.

    Args
        user_id (int): Идентификатор пользователя, для которого администратор подтверждает оплату.
        months (int): Количество месяцев подписки, за которые пользователь произвёл оплату.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура с кнопками "Подтвердить" и "Отменить".

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=f"admin_confirm:{user_id}:{months}:{premium}",
    )
    builder.button(
        text="❌ Отменить", callback_data=f"admin_decline:{user_id}:{months}:{premium}"
    )
    return builder.as_markup()
