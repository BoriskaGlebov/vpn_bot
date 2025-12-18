from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings_bot
from bot.subscription.enums import (
    AdminPaymentAction,
    SubscriptionAction,
    ToggleSubscriptionMode,
)


class SubscriptionCB(CallbackData, prefix="sub"):  # type: ignore[misc,call-arg]
    """CallbackData для действий с подпиской пользователя.

    Используется для кнопок выбора подписки и подтверждения оплаты.

    Attributes
        action (str): Тип действия. Возможные значения:
            - "select": пользователь выбирает период подписки (включая пробный).
            - "paid": пользователь подтверждает оплату.
        months (int): Количество месяцев или дней для подписки.
            Для пробного периода (trial) указывается количество дней.
            По умолчанию None.

    """

    action: str
    months: int = 0


class ToggleSubscriptionCB(CallbackData, prefix="toggle_sub"):  # type: ignore[misc,call-arg]
    """CallbackData для переключения режима подписки между стандартным и премиум.

    Используется для кнопок "Перейти в Премиум" или "Вернуться к стандартной подписке".

    Attributes
        mode (str): Режим подписки, который выбирает пользователь.
            Возможные значения:
                - "standard": стандартная подписка
                - "premium": премиум подписка

    Префикс CallbackData: "toggle_sub"

    """

    mode: str


class AdminPaymentCB(CallbackData, prefix="admin"):  # type: ignore[misc,call-arg]
    """CallbackData для подтверждения или отклонения оплаты администратором.

    Используется в админских кнопках для управления подписками пользователей.

    Attributes
        action (str): Действие админа. Возможные значения:
            - "confirm": подтверждение оплаты
            - "decline": отклонение оплаты
        user_id (int): Telegram ID пользователя, для которого выполняется действие.
        months (int): Количество месяцев подписки, за которые производится оплата.
        premium (bool, optional): Флаг, указывающий на премиум-подписку.
            По умолчанию False.

    """

    action: str
    user_id: int
    months: int
    premium: bool = False


def subscription_options_kb(
    premium: bool = False, trial: bool = False, founder: bool = False
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру с вариантами подписки.

    Пользователь может выбрать обычную или премиум-подписку.
    В премиум-режиме цены удваиваются, а описание опций обновляется.

    Args:
        founder (bool): Отключение кнопки премиум для основателей.
        premium (bool): Флаг премиум-режима (по умолчанию False).
        trial (bool): Пробный период, отключена если уже есть активная подписка

    Returns
        InlineKeyboardMarkup: Клавиатура с вариантами подписки.

    """
    price_map = settings_bot.price_map
    builder = InlineKeyboardBuilder()

    multiplier = 2 if premium else 1
    label_prefix = "⭐" if premium else "📆"

    options: list[tuple[str, int]] = []
    for m in (1, 3, 6, 12):
        price = price_map.get(m)
        if isinstance(price, int) and price >= 0:
            options.append((f"{m} месяц — {price * multiplier}₽", m))

    for label, months in options:
        builder.button(
            text=f"{label_prefix} {label}",
            callback_data=SubscriptionCB(
                action=SubscriptionAction.SELECT, months=months
            ),
        )

    # добавляем кнопку "Бесплатно" только для обычного режима
    if not premium and trial:
        builder.button(
            text="🎁 7 дней — Бесплатно",
            callback_data=SubscriptionCB(action=SubscriptionAction.SELECT, months=7),
        )

    # кнопка переключения режима
    if premium:
        builder.button(
            text="⬅️ Вернуться к стандартной подписке",
            callback_data=ToggleSubscriptionCB(mode=ToggleSubscriptionMode.STANDARD),
        )
    elif not founder:
        builder.button(
            text="🌟 Перейти в Премиум",
            callback_data=ToggleSubscriptionCB(mode=ToggleSubscriptionMode.PREMIUM),
        )

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
    builder.button(
        text="✅ Я оплатил",
        callback_data=SubscriptionCB(action=SubscriptionAction.PAID, months=months),
    )
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
        callback_data=AdminPaymentCB(
            action=AdminPaymentAction.CONFIRM,
            user_id=user_id,
            months=months,
            premium=premium,
        ),
    )
    builder.button(
        text="❌ Отменить",
        callback_data=AdminPaymentCB(
            action=AdminPaymentAction.DECLINE,
            user_id=user_id,
            months=months,
            premium=premium,
        ),
    )
    return builder.as_markup()
