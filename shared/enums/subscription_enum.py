from enum import Enum, StrEnum


class ToggleSubscriptionMode(StrEnum):
    """Режим переключения между типами подписки.

    Attributes
        STANDARD: Стандартный режим подписки.
        PREMIUM: Премиум-режим подписки.

    """

    STANDARD = "standard"
    PREMIUM = "premium"


class TrialStatus(str, Enum):
    """Статус активации пробного периода."""

    STARTED = "trial_started"
