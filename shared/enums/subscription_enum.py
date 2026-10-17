from enum import Enum, StrEnum


class ToggleSubscriptionMode(StrEnum):
    """Режим переключения между типами подписки.

    Attributes
        STANDARD: Стандартный режим подписки.
        PREMIUM: Премиум-режим подписки.
        FOUNDER: Подписка для основателей.
        ULTIMATE: Подписка без ограничений на количество устройств.

    """

    STANDARD = "standard"
    PREMIUM = "premium"
    FOUNDER = "founder"
    ULTIMATE = "ultimate"


class TrialStatus(str, Enum):
    """Статус активации пробного периода.

    Attributes
        STARTED: Создана новая trial-подписка.
        EXTENDED: Продлена уже существующая активная подписка (#283) —
            раньше оба случая отвечали одним и тем же "trial_started",
            хотя сервис мог как создать подписку, так и продлить
            существующую.

    """

    STARTED = "trial_started"
    EXTENDED = "trial_extended"


class SubscriptionInfoStatus(StrEnum):
    """Статус подписки в ответе `/subscriptions/info` (#282).

    Раньше `api/` отдавал эти три значения как сырые строки без
    перечисления, а `bot/` сравнивал их литералами в двух местах —
    опечатка в любой из четырёх точек молча ломала бы сравнение.

    Attributes
        ACTIVE: Подписка есть и активна.
        INACTIVE: Подписка есть, но не активна.
        NO_SUBSCRIPTION: У пользователя нет ни одной подписки.

    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    NO_SUBSCRIPTION = "no_subscription"
