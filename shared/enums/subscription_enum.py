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
    """Статус активации пробного периода."""

    STARTED = "trial_started"
