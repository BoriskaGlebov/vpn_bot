from enum import StrEnum, Enum


class ToggleSubscriptionMode(StrEnum):
    """Режим переключения между типами подписки.

    Attributes
        STANDARD: Стандартный режим подписки.
        PREMIUM: Премиум-режим подписки.

    """

    STANDARD = "standard"
    PREMIUM = "premium"



class SubscriptionEventType(str, Enum):
    USER_NOTIFY = "user_notify"
    ADMIN_NOTIFY = "admin_notify"
    DELETE_VPN_CONFIGS = "delete_vpn_configs"
    DELETE_PROXY = "delete_proxy"
