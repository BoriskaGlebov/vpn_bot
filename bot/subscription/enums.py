from enum import StrEnum


class SubscriptionAction(StrEnum):
    """Действия, связанные с выбором подписки.

    Attributes
        SELECT: Пользователь выбирает тип подписки.
        PAID: Подписка успешно оплачена.

    """

    SELECT = "select"
    PAID = "paid"


class ToggleSubscriptionMode(StrEnum):
    """Режим переключения между типами подписки.

    Attributes
        STANDARD: Стандартный режим подписки.
        PREMIUM: Премиум-режим подписки.

    """

    STANDARD = "standard"
    PREMIUM = "premium"


class AdminPaymentAction(StrEnum):
    """Действия администратора при обработке платежей.

    Attributes
        CONFIRM: Подтверждение оплаты администратором.
        DECLINE: Отклонение оплаты администратором.

    """

    CONFIRM = "confirm"
    DECLINE = "decline"
