from enum import StrEnum
from typing import Final

TRIAL_PERIOD_SENTINEL: Final = 7
"""Значение `months` в `SubscriptionCB`, обозначающее выбор пробного периода (7 дней), а не платной подписки."""


class SubscriptionAction(StrEnum):
    """Действия, связанные с выбором подписки.

    Attributes
        SELECT: Пользователь выбирает тип подписки.
        PAY_CARD: Пользователь выбрал оплату картой (автоматически, через платёжный шлюз).
        PAY_TRANSFER: Пользователь выбрал оплату переводом (вручную, с проверкой администратором).
        PAID: Пользователь подтвердил перевод ("Я оплатил") — ждём проверки администратором.
        CANCEL: Отмена

    """

    SELECT = "select"
    PAY_CARD = "pay_card"
    PAY_TRANSFER = "pay_transfer"
    PAID = "paid"
    CANCEL = "cancel"


class ToggleSubscriptionMode(StrEnum):
    """Режим переключения между типами подписки.

    Attributes
        STANDARD: Стандартный режим подписки.
        PREMIUM: Премиум-режим подписки.
        FOUNDER: Подписки основателей.
        ULTIMATE: Премиум-режим подписки без ограничений.

    """

    STANDARD = "standard"
    PREMIUM = "premium"
    FOUNDER = "founder"
    ULTIMATE = "ultimate"


class AdminPaymentAction(StrEnum):
    """Действия администратора при обработке платежей.

    Attributes
        CONFIRM: Подтверждение оплаты администратором.
        DECLINE: Отклонение оплаты администратором.

    """

    CONFIRM = "confirm"
    DECLINE = "decline"


class MySubscriptionAction(StrEnum):
    """Действия под карточкой "Моя подписка" главного меню.

    Attributes
        RENEW: Оформить новую или продлить текущую подписку.

    """

    RENEW = "renew"
