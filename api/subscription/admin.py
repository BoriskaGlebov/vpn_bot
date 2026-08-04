from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, ForeignKeyFilter
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from api.admin.badges import SUBSCRIPTION_BADGE_COLORS, badge
from api.subscription.models import Subscription
from api.users.models import User


def fmt_remaining_days(m: Subscription, _: str) -> str:
    """Форматер для оставшихся дней подписки."""
    value = m.remaining_days()
    return "∞" if value is None else str(value)


def fmt_type(m: Subscription, _: str) -> Markup:
    """Форматер для типа подписки цветным бейджем."""
    if not m.type:
        return Markup("-")
    return badge(m.type.name, SUBSCRIPTION_BADGE_COLORS.get(m.type.value, "secondary"))


def fmt_active(m: Subscription, _: str) -> Markup:
    """Форматер для статуса подписки."""
    return badge("активна", "success") if m.is_active else badge("нет", "secondary")


def fmt_user(m: Subscription, _: str) -> str:
    """Форматер для отображения пользователя."""
    return f"{m.user.username} ({m.user.telegram_id})" if m.user else "-"


class SubscriptionAdmin(ModelView, model=Subscription):
    """Админка для управления объектами Subscription.

    Позволяет:
        - Просматривать список подписок.
        - Просматривать детали подписки.
        - Редактировать подписки.
        - Фильтровать и искать подписки по пользователю и активности.

    Attributes
        name (str): Название модели в админке в единственном числе.
        name_plural (str): Название модели в админке во множественном числе.
        column_list (list[str]): Список колонок для отображения в таблице.
        column_sortable_list (list[str]): Список колонок, по которым можно сортировать.
        column_searchable_list (list[str]): Список колонок для поиска.
        column_filters (list[ColumnFilter]): Список фильтров для админки.
        form_columns (list[str]): Поля, доступные для редактирования в форме.
        column_labels (dict[str, str]): Подписи колонок в таблице.
        column_formatters (dict[str, Callable[[Any, str], Any]]): Форматирование значений колонок.
        can_create (bool): Разрешено ли создавать объекты.
        can_edit (bool): Разрешено ли редактировать объекты.
        can_delete (bool): Разрешено ли удалять объекты.
        can_view_details (bool): Разрешено ли просматривать детальную информацию.
        details_template (str): Кастомный шаблон для детального просмотра.

    """

    name = "Подписка"
    name_plural = "Подписки"
    icon = "fa-solid fa-calendar-check"

    column_list = [
        "id",
        "user",
        "type",
        "is_active",
        "start_date",
        "end_date",
        "remaining_days",
    ]

    column_sortable_list = [
        "id",
        "start_date",
        "end_date",
        "is_active",
        "type",
    ]

    column_searchable_list = [
        "user.username",
    ]

    column_filters = [
        BooleanFilter(Subscription.is_active, title="Активна"),
        ForeignKeyFilter(Subscription.user_id, User.username, title="Пользователь"),
    ]

    form_columns = [
        "user",
        "type",
        "is_active",
        "start_date",
        "end_date",
    ]

    column_labels = {
        "id": "ID",
        "user": "Пользователь",
        "type": "Тип",
        "is_active": "Активна",
        "start_date": "Начало",
        "end_date": "Конец",
        "remaining_days": "Дней осталось",
    }

    column_formatters = {
        "remaining_days": fmt_remaining_days,  # type: ignore[misc, dict-item]
        "type": fmt_type,  # type: ignore[misc, dict-item]
        "is_active": fmt_active,  # type: ignore[misc, dict-item]
        "user": fmt_user,  # type: ignore[misc, dict-item]
    }  # type: ignore[misc, assignment]

    can_create = True
    can_edit = True
    can_delete = False
    can_view_details = True
    details_template = "admin/subscription_details.html"

    def _with_eager_options(
        self, stmt: Select[tuple[Subscription]]
    ) -> Select[tuple[Subscription]]:
        """Добавляет к запросу предзагрузку пользователя.

        sqladmin открывает и закрывает свою сессию на каждый запрос
        (``ModelView._run_query``); без явного eager loading здесь
        обращение к ``Subscription.user`` в шаблоне/форматтере ``fmt_user``
        падает с ``DetachedInstanceError``/``MissingGreenlet``.
        """
        return stmt.options(selectinload(Subscription.user))

    def list_query(self, request: Request) -> Select[tuple[Subscription]]:
        """Запрос для списка подписок (все строки, без фильтра по pk)."""
        return self._with_eager_options(select(Subscription))

    def details_query(self, request: Request) -> Select[tuple[Subscription]]:
        """Запрос для страницы деталей — конкретная подписка по pk из URL.

        Важно: без ``self._stmt_by_identifier(...)`` запрос вернёт все строки
        таблицы, и sqladmin возьмёт первую попавшуюся (``rows[0]``) — то есть
        всегда одну и ту же подписку независимо от pk в адресе.
        """
        stmt = self._stmt_by_identifier(request.path_params["pk"])
        return self._with_eager_options(stmt)
