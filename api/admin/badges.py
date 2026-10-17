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


def badge(text: str, color: str) -> Markup:
    """Рендерит цветной Bootstrap/Tabler-бейдж.

    `text` экранируется — сейчас функция применяется только к значениям enum
    (роли, статусы), но она общая, и без экранирования применение к полю,
    которое заполняет пользователь, дало бы XSS в админке (см. #246).
    """
    return Markup('<span class="badge bg-{}">{}</span>').format(color, escape(text))
