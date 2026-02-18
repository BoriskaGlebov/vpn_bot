from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, ForeignKeyFilter

from bot.users.filters import ActiveSubscriptionFilter
from bot.users.models import Role, User


def format_role(obj: User, name: str) -> str:
    """Возвращает название роли пользователя."""
    return obj.role.name if obj.role else "-"


def format_current_subscription(obj: User, name: str) -> str:
    """Форматирует текущую подписку пользователя."""
    sub = obj.current_subscription
    if sub:
        return (
            f"{sub.type.name if sub.type else 'Без подписки'} "
            f"до {sub.end_date.strftime('%Y-%m-%d') if sub.end_date else '∞'}"
        )
    return "-"


def format_files_count(obj: User, name: str) -> int:
    """Возвращает количество VPN конфигов пользователя."""
    return len(obj.vpn_configs) if obj.vpn_configs else 0


class UserAdmin(ModelView, model=User):
    """Админка для управления пользователями.

    В этой админке:
    - Редактируются только поля пользователя;
    - Связанные объекты (подписки, VPN конфиги) только для просмотра.
    """

    column_list = [
        "id",
        "telegram_id",
        "username",
        "first_name",
        "last_name",
        "role",
        "has_used_trial",
        "current_subscription",
        "vpn_files_count",
    ]
    column_sortable_list = [
        "id",
        "telegram_id",
        "username",
        "vpn_files_count",
    ]
    details_template = "admin/user_details.html"
    column_searchable_list = ["username", "first_name", "last_name"]
    column_filters = [
        BooleanFilter(User.has_used_trial, title="Использовал триал"),
        ForeignKeyFilter(User.role_id, Role.name, title="Роль"),
        ActiveSubscriptionFilter(),
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    column_labels = {
        "id": "ID",
        "telegram_id": "Telegram ID",
        "username": "Имя пользователя",
        "first_name": "Имя",
        "last_name": "Фамилия",
        "role": "Роль",
        "has_used_trial": "Использовал триал",
        "current_subscription": "Текущая подписка",
        "vpn_files_count": "Количество конфиг файлов",
    }
    column_formatters = {
        "role": format_role,
        "current_subscription": format_current_subscription,
        "format_files_count": format_files_count,
        User.username: lambda m, a: m.username[:10],
    }
    name = "Пользователь"
    name_plural = "Пользователи"
    form_columns = [
        "telegram_id",
        "username",
        "first_name",
        "last_name",
        "role",
        "has_used_trial",
    ]
    readonly_columns = [
        "current_subscription",
        "vpn_files_count",
    ]


def format_users_count(obj: Role, name: str) -> int:
    """Возвращает количество пользователей, связанных с ролью.

    Args:
        obj (Role): Экземпляр роли.
        name (str): Имя колонки (не используется, требуется API sqladmin).

    Returns
        int: Количество пользователей.

    """
    return len(obj.users) if obj.users else 0


class RoleAdmin(ModelView, model=Role):
    """Админка для управления ролями пользователей.

    Отображает список ролей, количество пользователей в каждой роли,
    детальную информацию и позволяет фильтровать и сортировать роли.

    Attributes
        column_list (list[str | Any]): Колонки, отображаемые в списке ролей.
        column_details_list (list[str | Any]): Колонки, отображаемые на детальной странице.
        details_template (str): Путь к кастомному шаблону детальной страницы.
        column_sortable_list (list[str | Any]): Колонки, доступные для сортировки.
        column_searchable_list (list[str | Any]): Колонки, по которым возможен поиск.
        column_formatters (dict[str, callable]): Функции форматирования колонок.
        can_create (bool): Разрешено ли создавать новые записи.
        can_edit (bool): Разрешено ли редактировать записи.
        can_delete (bool): Разрешено ли удалять записи.
        column_labels (dict[str, str]): Человеко-понятные метки колонок.
        name (str): Название модели в единственном числе.
        name_plural (str): Название модели во множественном числе.
        form_columns (list[str]): Поля, доступные для редактирования.

    """

    column_list = [Role.id, Role.name, Role.description, "users_count"]
    column_details_list = [
        Role.id,
        Role.name,
        Role.description,
    ]
    details_template = "admin/role_details.html"
    column_sortable_list = [Role.id, Role.name]
    column_searchable_list = [Role.name, Role.description]
    column_formatters = {
        "users_list": lambda m, a: (
            ", ".join(str(u) for u in m.users) if m.users else "-"
        ),
        "users_count": format_users_count,
    }

    can_create = False
    can_edit = False
    can_delete = False

    column_labels = {
        "id": "ID",
        "name": "Название роли",
        "description": "Описание роли",
        "users_count": "Количество пользователей",
    }
    name = "Роль"
    name_plural = "Роли"
    form_columns = ["name", "description", "users"]
