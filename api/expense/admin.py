from typing import Any

from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from starlette.requests import Request

from api.admin.badges import (
    EXPENSE_CATEGORY_BADGE_COLORS,
    EXPENSE_CATEGORY_LABELS,
    badge,
)
from api.core.config import settings_api
from api.expense.models import Expense
from shared.enums.expense_enum import ExpenseCategory


def fmt_category(m: Expense, _: str) -> Markup:
    """Форматер категории расхода цветным бейджем."""
    value = m.category.value
    return badge(
        EXPENSE_CATEGORY_LABELS.get(value, value),
        EXPENSE_CATEGORY_BADGE_COLORS.get(value, "secondary"),
    )


def fmt_amount(m: Expense, _: str) -> str:
    """Форматер суммы расхода с разделителем тысяч и знаком ₽."""
    return f"{m.amount:,}₽".replace(",", " ")


def fmt_recurring(m: Expense, _: str) -> Markup:
    """Форматер периодичности бейджем."""
    if m.is_recurring:
        return badge("ежемесячный", "teal")
    return badge("разовый", "secondary")


def fmt_node(m: Expense, _: str) -> str:
    """Форматер имени ноды с безопасным дефолтом."""
    return m.node_name or "—"


class ExpenseAdmin(ModelView, model=Expense):
    """Административное представление модели Expense."""

    name = "Расход"
    name_plural = "Расходы"
    icon = "fa-solid fa-wallet"

    column_list = [
        "id",
        "amount",
        "category",
        "description",
        "period_start",
        "node_name",
        "is_recurring",
        "created_at",
    ]

    column_sortable_list = [
        "id",
        "amount",
        "period_start",
        "category",
        "is_recurring",
        "created_at",
    ]

    column_searchable_list = [
        "description",
        "node_name",
    ]

    column_filters = [
        StaticValuesFilter(
            Expense.category,
            values=[
                (c.value, EXPENSE_CATEGORY_LABELS[c.value]) for c in ExpenseCategory
            ],
            title="Категория",
        ),
        BooleanFilter(Expense.is_recurring, title="Ежемесячный"),
    ]

    column_default_sort = ("period_start", True)

    form_columns = [
        "amount",
        "category",
        "description",
        "period_start",
        "period_end",
        "node_name",
        "is_recurring",
    ]

    column_labels = {
        "id": "ID",
        "amount": "Сумма",
        "category": "Категория",
        "description": "Описание",
        "period_start": "Начало периода",
        "period_end": "Конец периода",
        "node_name": "Нода",
        "is_recurring": "Периодичность",
        "created_at": "Создано",
        "updated_at": "Обновлено",
    }

    column_formatters = {
        "category": fmt_category,  # type: ignore[misc, dict-item]
        "amount": fmt_amount,  # type: ignore[misc, dict-item]
        "is_recurring": fmt_recurring,  # type: ignore[misc, dict-item]
        "node_name": fmt_node,  # type: ignore[misc, dict-item]
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Expense,
        is_created: bool,
        request: Request,
    ) -> None:
        """Валидирует имя ноды при создании и редактировании записи.

        Если `vpn_node_names` пустое (тесты, минимальный конфиг), валидация
        пропускается — поведение идентично `ExpenseService._validate_node_name`.

        Args:
            data: Данные формы.
            model: Изменяемый объект модели.
            is_created: True при создании, False при редактировании.
            request: Текущий HTTP-запрос SQLAdmin.

        Raises
            ValueError: Имя ноды не найдено в конфигурации — SQLAdmin
                показывает сообщение как ошибку формы.

        """
        node_name: str | None = data.get("node_name") or None
        if node_name is None:
            return
        known = settings_api.vpn_node_names
        if known and node_name not in known:
            raise ValueError(
                f"Нода «{node_name}» не найдена в конфигурации. "
                f"Допустимые значения: {', '.join(sorted(known))}."
            )
