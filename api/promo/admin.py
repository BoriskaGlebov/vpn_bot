from typing import Any

from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, ForeignKeyFilter, OperationColumnFilter
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from api.admin.badges import (
    PROMO_DISCOUNT_TYPE_COLORS,
    PROMO_DISCOUNT_TYPE_LABELS,
    badge,
)
from api.promo.models import PromoCode, PromoCodeUsage
from api.users.models import User


def fmt_discount_type(m: PromoCode, _: str) -> Markup:
    """Форматер типа скидки цветным бейджем."""
    value = m.discount_type.value
    return badge(
        PROMO_DISCOUNT_TYPE_LABELS.get(value, value),
        PROMO_DISCOUNT_TYPE_COLORS.get(value, "secondary"),
    )


def fmt_discount_value(m: PromoCode, _: str) -> str:
    """Форматер величины скидки с единицей измерения."""
    return (
        f"{m.discount_value}%"
        if m.discount_type.value == "percent"
        else f"{m.discount_value}₽"
    )


def fmt_usage_limit(m: PromoCode, _: str) -> str:
    """Форматер "использовано/лимит" для списка промокодов."""
    limit = m.max_uses if m.max_uses is not None else "∞"
    return f"{m.used_count}/{limit}"


def fmt_promo_code(m: PromoCodeUsage, _: str) -> str:
    """Форматер промокода в списке применений."""
    return m.promo_code.code if m.promo_code else "-"


def fmt_usage_user(m: PromoCodeUsage, _: str) -> str:
    """Форматер пользователя в списке применений промокода."""
    return f"{m.user.username} ({m.user.telegram_id})" if m.user else "-"


class PromoCodeAdmin(ModelView, model=PromoCode):
    """Админка для создания и управления промокодами."""

    name = "Промокод"
    name_plural = "Промокоды"
    icon = "fa-solid fa-tag"

    column_list = [
        "id",
        "code",
        "discount_type",
        "discount_value",
        "used_count",
        "max_uses",
        "valid_from",
        "valid_until",
        "is_active",
    ]

    column_sortable_list = [
        "id",
        "code",
        "used_count",
        "max_uses",
        "valid_from",
        "valid_until",
        "is_active",
    ]

    column_searchable_list = ["code"]

    column_filters = [
        BooleanFilter(PromoCode.is_active, title="Активен"),
        OperationColumnFilter(PromoCode.valid_until),
    ]

    form_columns = [
        "code",
        "discount_type",
        "discount_value",
        "max_uses",
        "valid_from",
        "valid_until",
        "is_active",
    ]

    column_labels = {
        "id": "ID",
        "code": "Код",
        "discount_type": "Тип скидки",
        "discount_value": "Величина",
        "used_count": "Применений",
        "max_uses": "Лимит",
        "valid_from": "Действует с",
        "valid_until": "Действует до",
        "is_active": "Активен",
    }

    column_formatters = {
        "discount_type": fmt_discount_type,  # type: ignore[misc, dict-item]
        "discount_value": fmt_discount_value,  # type: ignore[misc, dict-item]
        "used_count": fmt_usage_limit,  # type: ignore[misc, dict-item]
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    details_template = "admin/promo_code_details.html"

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: PromoCode,
        is_created: bool,
        request: Request,
    ) -> None:
        """Нормализует код в верхний регистр при создании/редактировании в админке.

        `PromoService.validate_code` нормализует введённый пользователем код
        тем же образом — без этого код, заведённый админом в смешанном
        регистре, никогда бы не совпал при проверке.
        """
        if "code" in data and data["code"]:
            data["code"] = data["code"].strip().upper()

    def _with_eager_options(
        self, stmt: Select[tuple[PromoCode]]
    ) -> Select[tuple[PromoCode]]:
        """Добавляет предзагрузку применений промокода вместе с пользователями.

        sqladmin открывает и закрывает свою сессию на каждый запрос
        (``ModelView._run_query``); без явного eager loading здесь обращение
        к ``PromoCode.usages`` (``lazy="raise"``) в шаблоне
        ``promo_code_details.html`` падает с ошибкой.
        """
        return stmt.options(
            selectinload(PromoCode.usages).selectinload(PromoCodeUsage.user)
        )

    def list_query(self, request: Request) -> Select[tuple[PromoCode]]:
        """Запрос для списка промокодов (все строки, без фильтра по pk)."""
        return self._with_eager_options(select(PromoCode))

    def details_query(self, request: Request) -> Select[tuple[PromoCode]]:
        """Запрос для страницы деталей — конкретный промокод по pk из URL.

        Важно: без ``self._stmt_by_identifier(...)`` запрос вернёт все строки
        таблицы, и sqladmin возьмёт первую попавшуюся.
        """
        stmt = self._stmt_by_identifier(request.path_params["pk"])
        return self._with_eager_options(stmt)


class PromoCodeUsageAdmin(ModelView, model=PromoCodeUsage):
    """Админка статистики применений промокодов (только просмотр)."""

    name = "Применение промокода"
    name_plural = "Применения промокодов"
    icon = "fa-solid fa-receipt"

    column_list = [
        "id",
        "promo_code",
        "user",
        "discount_amount",
        "used_at",
    ]

    column_sortable_list = ["id", "used_at", "discount_amount"]

    column_searchable_list = ["user.username"]

    column_filters = [
        ForeignKeyFilter(
            PromoCodeUsage.promo_code_id, PromoCode.code, title="Промокод"
        ),
        ForeignKeyFilter(PromoCodeUsage.user_id, User.username, title="Пользователь"),
    ]

    column_labels = {
        "id": "ID",
        "promo_code": "Промокод",
        "user": "Пользователь",
        "discount_amount": "Скидка, ₽",
        "used_at": "Когда",
    }

    column_formatters = {
        "promo_code": fmt_promo_code,  # type: ignore[misc, dict-item]
        "user": fmt_usage_user,  # type: ignore[misc, dict-item]
    }

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
