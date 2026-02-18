from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, ForeignKeyFilter, OperationColumnFilter

from bot.referrals.models import Referral
from bot.users.models import User


class ReferralAdmin(ModelView, model=Referral):
    """Админка для управления рефералами.

    В этой админке отображаются все рефералы с возможностью сортировки,
    поиска и фильтрации по пользователям и дате выдачи бонуса.

    Attributes
        name (str): Название модели в единственном числе для админки.
        name_plural (str): Название модели во множественном числе для админки.
        column_list (list[str]): Колонки, отображаемые в таблице.
        column_sortable_list (list[str]): Колонки, по которым возможна сортировка.
        column_searchable_list (list[str]): Колонки, по которым возможен поиск.
        column_filters (list[Any]): Фильтры для админки.
        form_columns (list[str]): Поля, доступные для редактирования.
        column_labels (dict[str, str]): Подписи колонок.
        column_formatters (dict[str, callable]): Форматирование отображения значений.
        can_create (bool): Разрешено ли создавать новые записи.
        can_edit (bool): Разрешено ли редактировать записи.
        can_delete (bool): Разрешено ли удалять записи.
        can_view_details (bool): Разрешено ли просматривать детальную информацию.

    """

    name = "Реферал"
    name_plural = "Рефералы"

    column_list = [
        "id",
        "inviter",
        "invited",
        "bonus_given",
        "bonus_given_at",
    ]

    column_sortable_list = [
        "id",
        "bonus_given",
        "bonus_given_at",
        "inviter_id",
        "invited_id",
    ]

    column_searchable_list = [
        "inviter.username",
        "invited.username",
    ]

    column_filters = [
        BooleanFilter(Referral.bonus_given, title="Бонус выдан"),
        ForeignKeyFilter(Referral.inviter_id, User.username, title="Пригласил"),
        ForeignKeyFilter(Referral.invited_id, User.username, title="Приглашён"),
        OperationColumnFilter(Referral.bonus_given_at),
    ]

    form_columns = [
        "inviter",
        "invited",
        "bonus_given",
        "bonus_given_at",
    ]

    column_labels = {
        "id": "ID",
        "inviter": "Кто пригласил",
        "invited": "Кого пригласили",
        "bonus_given": "Бонус выдан",
        "bonus_given_at": "Дата выдачи бонуса",
    }

    column_formatters = {
        "inviter": lambda m, a: (
            f"{m.inviter.username} ({m.inviter.telegram_id})" if m.inviter else "-"
        ),
        "invited": lambda m, a: (
            f"{m.invited.username} ({m.invited.telegram_id})" if m.invited else "-"
        ),
        "bonus_given": lambda m, a: ("✅ Да" if m.bonus_given else "❌ Нет"),
        "bonus_given_at": lambda m, a: (
            m.bonus_given_at.strftime("%Y-%m-%d %H:%M") if m.bonus_given_at else "-"
        ),
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
