from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.subscription.enums import (
    TRIAL_PERIOD_SENTINEL,
    AdminPaymentAction,
    MySubscriptionAction,
    SubscriptionAction,
    ToggleSubscriptionMode,
)
from bot.subscription.utils.sub_utils import get_correct_price_map


class SubscriptionCB(CallbackData, prefix="sub"):  # type: ignore[misc,call-arg]
    """CallbackData для действий с подпиской пользователя.

    Используется для кнопок выбора подписки, выбора способа оплаты
    и подтверждения оплаты.

    Attributes
        action (SubscriptionAction): Тип действия. Возможные значения:
            - "select": пользователь выбирает период подписки (включая пробный).
            - "pay_card": пользователь выбрал оплату картой (автоматически).
            - "pay_transfer": пользователь выбрал оплату переводом (вручную).
            - "paid": пользователь подтверждает перевод ("Я оплатил").
            - "cancel": отмена оформления подписки.
        months (int): Количество месяцев или дней для подписки.
            Для пробного периода (trial) указывается количество дней.
            По умолчанию None.
        founder (bool): Указать основателя если спец цена.
        transaction_id (UUID | None): идентификатор транзакции

    """

    action: SubscriptionAction
    months: int = 0
    founder: bool = False
    transaction_id: UUID | None = None


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
        transaction_id (UUID): идентификатор платежки

    """

    action: str
    user_id: int
    months: int
    premium: bool = False
    transaction_id: UUID


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
    price_map = get_correct_price_map(premium=premium, founder=founder)

    builder = InlineKeyboardBuilder()

    label_prefix = "⭐" if premium else "📆"

    options: list[tuple[str, int]] = []
    for m in (1, 3, 6, 12):
        price = price_map.get(m)
        if m == 12 and isinstance(price, int) and price >= 0:
            options.append((f"{m}мес. — 🔥 {price}₽", m))
        elif isinstance(price, int) and price >= 0:
            options.append((f"{m} мес. — {price}₽", m))

    for label, months in options:
        builder.button(
            text=f"{label_prefix} {label}",
            callback_data=SubscriptionCB(
                action=SubscriptionAction.SELECT, months=months, founder=founder
            ),
        )

    if not premium and not founder and not trial:
        builder.button(
            text="🎁 7 дней — Бесплатно",
            callback_data=SubscriptionCB(
                action=SubscriptionAction.SELECT, months=TRIAL_PERIOD_SENTINEL
            ),
        )

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

    builder.button(
        text="❌ Отмена", callback_data=SubscriptionCB(action=SubscriptionAction.CANCEL)
    )
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def payment_method_kb(
    months: int,
    founder: bool,
    transaction_id: UUID,
    has_card_option: bool,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру выбора способа оплаты.

    Args
        months (int): Количество месяцев выбранной подписки.
        founder (bool): Проверка на основателя.
        transaction_id (UUID): Идентификатор созданной транзакции.
        has_card_option (bool): Показывать ли оплату картой (платёжный шлюз
            вернул ссылку при создании транзакции). Перевод доступен всегда.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками "Оплата картой" (опционально),
        "Оплата переводом" и "Отмена".

    """
    builder = InlineKeyboardBuilder()
    if has_card_option:
        builder.button(
            text="💳 Оплата картой",
            callback_data=SubscriptionCB(
                action=SubscriptionAction.PAY_CARD,
                months=months,
                founder=founder,
                transaction_id=transaction_id,
            ),
        )
    builder.button(
        text="💵 Оплата переводом",
        callback_data=SubscriptionCB(
            action=SubscriptionAction.PAY_TRANSFER,
            months=months,
            founder=founder,
            transaction_id=transaction_id,
        ),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=SubscriptionCB(
            action=SubscriptionAction.CANCEL,
            transaction_id=transaction_id,
            founder=founder,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def card_payment_kb(
    transaction_id: UUID,
    payment_url: str,
    founder: bool,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для оплаты картой через платёжный шлюз.

    Подтверждение оплаты автоматическое (по вебхуку от платёжного шлюза),
    поэтому кнопки "Я оплатил" здесь нет — только ссылка на оплату и отмена.

    Args
        transaction_id (UUID): Идентификатор транзакции.
        payment_url (str): Ссылка на страницу оплаты картой.
        founder (bool): Проверка на основателя.

    Returns
        InlineKeyboardMarkup: Клавиатура со ссылкой на оплату и кнопкой "Отмена".

    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💳 Перейти к оплате",
            url=payment_url,
        )
    )
    builder.button(
        text="❌ Отмена",
        callback_data=SubscriptionCB(
            action=SubscriptionAction.CANCEL,
            transaction_id=transaction_id,
            founder=founder,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def transfer_payment_kb(
    months: int,
    founder: bool,
    transaction_id: UUID,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для оплаты переводом.

    Оплата проверяется администратором вручную: пользователь переводит
    деньги по реквизитам из сообщения и нажимает "Я оплатил", после чего
    администратор подтверждает или отклоняет платёж.

    Args
        months (int): Количество месяцев подписки.
        founder (bool): Проверка на основателя.
        transaction_id (UUID): Идентификатор транзакции.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками "Я оплатил" и "Отмена".

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Я оплатил",
        callback_data=SubscriptionCB(
            action=SubscriptionAction.PAID,
            months=months,
            founder=founder,
            transaction_id=transaction_id,
        ),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=SubscriptionCB(
            action=SubscriptionAction.CANCEL,
            transaction_id=transaction_id,
            founder=founder,
        ),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_payment_kb(
    user_id: int, months: int, premium: bool, transaction_id: UUID
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для администраторов для подтверждения или отклонения оплаты пользователя.

    Args
        user_id (int): Идентификатор пользователя, для которого администратор подтверждает оплату.
        months (int): Количество месяцев подписки, за которые пользователь произвёл оплату.
        transaction_id (UUID): Идентификатор транзакции

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
            transaction_id=transaction_id,
        ),
    )
    builder.button(
        text="❌ Отменить",
        callback_data=AdminPaymentCB(
            action=AdminPaymentAction.DECLINE,
            user_id=user_id,
            months=months,
            premium=premium,
            transaction_id=transaction_id,
        ),
    )
    return builder.as_markup()


class MySubscriptionCB(CallbackData, prefix="my_sub"):  # type: ignore[misc,call-arg]
    """CallbackData для действий под карточкой "Моя подписка" главного меню.

    Attributes
        action (MySubscriptionAction): Выбранное действие — оформить/продлить
            подписку.

    """

    action: MySubscriptionAction


def my_subscription_menu_kb() -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру под карточкой "Моя подписка".

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопкой "Оформить/продлить подписку".

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Оформить / продлить подписку",
        callback_data=MySubscriptionCB(action=MySubscriptionAction.RENEW),
    )
    builder.adjust(1)
    return builder.as_markup()
