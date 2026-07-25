from markupsafe import Markup

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
    "PAID": "success",
    "PENDING": "warning",
    "FAILED": "danger",
    "CANCELED": "secondary",
}


def badge(text: str, color: str) -> Markup:
    """Рендерит цветной Bootstrap/Tabler-бейдж."""
    return Markup(f'<span class="badge bg-{color}">{text}</span>')
