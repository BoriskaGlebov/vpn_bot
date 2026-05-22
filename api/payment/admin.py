from datetime import datetime

from markupsafe import Markup
from sqladmin import ModelView

from api.payment.model import PaymentTransaction


def format_status(obj: PaymentTransaction, name: str) -> str:
    """Форматирует статус платежа с цветовым выделением.

    Args:
        obj: Экземпляр PaymentTransaction.
        name: Имя поля (требуется sqladmin, не используется).

    Returns
        HTML-строка с цветным статусом.

    """
    status = obj.status.value

    colors: dict[str, str] = {
        "PAID": "green",
        "PENDING": "orange",
        "FAILED": "red",
        "CANCELED": "gray",
    }

    color = colors.get(status, "black")

    return Markup(f'<span style="color:{color}; font-weight:600">{status}</span>')


def format_source(obj: PaymentTransaction, name: str) -> str:
    """Форматирует источник платежа."""
    return obj.source.value if obj.source else "-"


def format_user(obj: PaymentTransaction, name: str) -> str:
    """Возвращает Telegram ID пользователя."""
    user = obj.user
    return str(user.telegram_id) if user else "-"


def format_admin(obj: PaymentTransaction, name: str) -> str:
    """Форматирует администратора (создатель/подтверждающий)."""
    admin = getattr(obj, name, None)
    return str(admin.telegram_id) if admin else "-"


def format_datetime(obj: PaymentTransaction, name: str) -> str:
    """Форматирует datetime поля в читаемый вид.

    Args:
        obj: PaymentTransaction.
        name: имя атрибута datetime поля.

    Returns
        Отформатированная дата или '-'.

    """
    value: datetime | None = getattr(obj, name)
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "-"


def format_amount(obj: PaymentTransaction, name: str) -> str:
    """Форматирует сумму платежа с валютой."""
    return f"{obj.amount} {obj.currency}"


class PaymentTransactionAdmin(ModelView, model=PaymentTransaction):
    """Админ-панель для управления платежными транзакциями.

    Отображает:
        - информацию о пользователе
        - статус платежа
        - источник создания
        - данные подписки
        - аудит администраторов
        - данные платежного шлюза
    """

    column_list = [
        PaymentTransaction.id,
        "user",
        "amount",
        # "currency",
        "status",
        "source",
        PaymentTransaction.subscription_months,
        PaymentTransaction.is_premium,
        PaymentTransaction.is_founder,
        "created_by_admin",
        "confirmed_by_admin",
        PaymentTransaction.gateway_transaction_id,
        PaymentTransaction.paid_at,
        PaymentTransaction.confirmed_at,
    ]

    column_details_list = column_list + [
        PaymentTransaction.gateway_payload,
        PaymentTransaction.description,
    ]

    column_searchable_list = [
        "gateway_transaction_id",
        "user_id",
    ]

    column_sortable_list = [
        PaymentTransaction.id,
        PaymentTransaction.amount,
        PaymentTransaction.status,
        PaymentTransaction.created_by_admin_id,
    ]

    column_labels = {
        "id": "ID",
        "user": "Пользователь",
        "amount": "Сумма",
        "currency": "Валюта",
        "status": "Статус",
        "source": "Источник",
        "subscription_months": "Месяцы подписки",
        "is_premium": "Premium",
        "is_founder": "Founder",
        "created_by_admin": "Создал админ",
        "confirmed_by_admin": "Подтвердил админ",
        "gateway_transaction_id": "ID платежки",
        "gateway_payload": "Payload",
        "description": "Описание",
        "paid_at": "Оплачен",
        "confirmed_at": "Подтверждён",
    }

    column_formatters = {
        "status": format_status,  # type: ignore[misc, dict-item]
        "source": format_source,  # type: ignore[misc, dict-item]
        "user": format_user,  # type: ignore[misc, dict-item]
        "created_by_admin": format_admin,  # type: ignore[misc, dict-item]
        "confirmed_by_admin": format_admin,  # type: ignore[misc, dict-item]
        "amount": format_amount,  # type: ignore[misc, dict-item]
        "paid_at": format_datetime,  # type: ignore[misc, dict-item]
        "confirmed_at": format_datetime,  # type: ignore[misc, dict-item]
    }

    readonly_columns = [
        "gateway_payload",
        "gateway_transaction_id",
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    name = "Платеж"
    name_plural = "Платежи"
