from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, ForeignKeyFilter

from bot.subscription.models import Subscription
from bot.users.models import User


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
        "remaining_days": lambda m, a: (
            "∞" if m.remaining_days() is None else m.remaining_days()
        ),
        "type": lambda m, a: (m.type.value.upper() if m.type else "-"),
        "is_active": lambda m, a: ("🟢 АКТИВНА" if m.is_active else "🔴 НЕТ"),
        "user": lambda m, a: (
            f"{m.user.username} ({m.user.telegram_id})" if m.user else "-"
        ),
    }

    can_create = True
    can_edit = True
    can_delete = False
    can_view_details = True
    details_template = "admin/subscription_details.html"
