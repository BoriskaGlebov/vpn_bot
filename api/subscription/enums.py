from enum import Enum, StrEnum


class ToggleSubscriptionMode(StrEnum):
    """Режим переключения между типами подписки.

    Attributes
        STANDARD: Стандартный режим подписки.
        PREMIUM: Премиум-режим подписки.

    """

    STANDARD = "standard"
    PREMIUM = "premium"


class SubscriptionEventType(str, Enum):
    """Типы событий, используемых в системе подписок.

    Эти значения применяются для маршрутизации и обработки доменных событий,
    связанных с пользователями и их подписками.

    Attributes
        USER_NOTIFY: Событие пользовательского уведомления.
        ADMIN_NOTIFY: Событие уведомления администратора.
        DELETE_VPN_CONFIGS: Событие удаления VPN конфигураций пользователя.
        DELETE_PROXY: Событие удаления proxy конфигураций пользователя.

    """

    USER_NOTIFY = "user_notify"
    ADMIN_NOTIFY = "admin_notify"
    DELETE_VPN_CONFIGS = "delete_vpn_configs"
    DELETE_PROXY = "delete_proxy"


class TrialStatus(str, Enum):
    """Статус активации пробного периода."""

    STARTED = "trial_started"
