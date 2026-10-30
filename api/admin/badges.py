from markupsafe import Markup, escape

ROLE_BADGE_COLORS = {
    "admin": "red",
    "founder": "purple",
    "user": "secondary",
}

SUBSCRIPTION_BADGE_COLORS = {
    "trial": "orange",
    "standard": "secondary",
    "premium": "teal",
    "founder": "purple",
    "ultimate": "indigo",
}

PAYMENT_BADGE_COLORS = {
    "paid": "success",
    "pending": "warning",
    "failed": "danger",
    "canceled": "secondary",
}

VPN_CONFIG_BADGE_COLORS = {
    "active": "success",
    "pending_delete": "warning",
    "deleted": "secondary",
}

VPN_CONFIG_STATUS_LABELS = {
    "active": "Активен",
    "pending_delete": "Ожидает удаления",
    "deleted": "Удалён",
}

VPN_BACKEND_BADGE_COLORS = {
    "amnezia": "teal",
    "xray": "indigo",
}

VPN_BACKEND_LABELS = {
    "amnezia": "AmneziaWG",
    "xray": "XRay/VLESS",
}

# protocol хранит значения VPNProtocol (shared/enums/vpn_enum.py), для
# XRay-подписки — несколько значений через запятую, см. VPNConfig.protocol.
VPN_PROTOCOL_LABELS = {
    "wg_v1": "WireGuard v1",
    "wg_v2": "WireGuard v2",
    "wg_v3": "WireGuard v3",
    "vless_reality_tcp": "VLESS Reality TCP",
    "vless_reality_xhttp": "VLESS Reality XHTTP",
}


PROMO_DISCOUNT_TYPE_COLORS = {
    "percent": "teal",
    "fixed": "indigo",
}

PROMO_DISCOUNT_TYPE_LABELS = {
    "percent": "Процент",
    "fixed": "Фикс. сумма",
}


def badge(text: str, color: str) -> Markup:
    """Рендерит цветной Bootstrap/Tabler-бейдж.

    `text` экранируется — сейчас функция применяется только к значениям enum
    (роли, статусы), но она общая, и без экранирования применение к полю,
    которое заполняет пользователь, дало бы XSS в админке.
    """
    return Markup('<span class="badge bg-{}">{}</span>').format(color, escape(text))
