from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import ForeignKeyFilter, OperationColumnFilter

from api.admin.badges import VPN_CONFIG_BADGE_COLORS, VPN_CONFIG_STATUS_LABELS, badge
from api.users.models import User
from api.vpn.models import VPNConfig


def format_user(obj: VPNConfig, name: str) -> str:
    """Форматирует отображение пользователя в списке.

    Args
        obj: Экземпляр VPNConfig.
        name: Имя поля (требуется sqladmin, не используется).

    Returns
        str: Строка формата
            "<username> (<telegram_id>)"
            или "-" если пользователь отсутствует.

    """
    if obj.user is None:
        return "-"
    return f"{obj.user.username} ({obj.user.telegram_id})"


def format_pub_key(obj: VPNConfig, name: str) -> str:
    """Форматирует публичный ключ для отображения.

    Обрезает ключ до 25 символов для компактного вывода.

    Args
        obj: Экземпляр VPNConfig.
        name: Имя поля (требуется sqladmin, не используется).

    Returns
        str: Укороченный публичный ключ или "-".

    """
    if not obj.pub_key:
        return "-"
    return f"{obj.pub_key[:25]}..."


def format_status(obj: VPNConfig, name: str) -> Markup:
    """Форматирует статус конфига цветным бейджем.

    Args
        obj: Экземпляр VPNConfig.
        name: Имя поля (требуется sqladmin, не используется).

    Returns
        Markup с цветным бейджем статуса.

    """
    status = obj.status.value
    label = VPN_CONFIG_STATUS_LABELS.get(status, status)
    color = VPN_CONFIG_BADGE_COLORS.get(status, "dark")
    return badge(label, color)


class VPNConfigAdmin(ModelView, model=VPNConfig):
    """Административное представление модели VPNConfig.

    Конфигурирует:
        - список отображаемых колонок,
        - сортировку и поиск,
        - фильтрацию,
        - форму редактирования,
        - форматирование отображаемых значений,
        - права доступа к операциям.

    Attributes
        name (str): Отображаемое имя модели в админке.
        name_plural (str): Отображаемое имя во множественном числе.
        column_list (list[str]): Колонки, отображаемые в таблице.
        column_sortable_list (list[str]): Колонки, доступные для сортировки.
        column_searchable_list (list[str]): Колонки, участвующие в поиске.
        column_filters (list[Any]): Фильтры в правой панели.
        form_columns (list[str]): Поля формы создания/редактирования.
        column_labels (dict[str, str]): Отображаемые подписи колонок.
        column_formatters (dict[str, Any]): Кастомные форматтеры колонок.
        can_create (bool): Разрешено ли создание записи.
        can_edit (bool): Разрешено ли редактирование записи.
        can_delete (bool): Разрешено ли удаление записи.
        can_view_details (bool): Разрешён ли просмотр деталей.
        details_template (str): Шаблон страницы деталей.

    """

    name = "VPN конфиг"
    name_plural = "VPN конфиги"
    icon = "fa-solid fa-network-wired"

    column_list = [
        "id",
        "user",
        "file_name",
        "pub_key",
        "status",
        "created_at",
    ]

    column_sortable_list = [
        "id",
        "file_name",
        "user_id",
        "status",
        "created_at",
    ]

    column_searchable_list = [
        "file_name",
        "pub_key",
        "user.username",
    ]

    column_filters = [
        ForeignKeyFilter(VPNConfig.user_id, User.username, title="Пользователь"),
        OperationColumnFilter(VPNConfig.file_name),
        OperationColumnFilter(VPNConfig.status),
    ]

    form_columns = [
        "user",
        "file_name",
        "pub_key",
    ]

    column_labels = {
        "id": "ID",
        "user": "Пользователь",
        "file_name": "Имя файла",
        "pub_key": "Public key",
        "status": "Статус",
        "created_at": "Дата создания",
    }

    column_formatters = {
        "user": format_user,  # type: ignore[misc, dict-item]
        "pub_key": format_pub_key,  # type: ignore[misc, dict-item]
        "status": format_status,  # type: ignore[misc, dict-item]
    }

    can_create = True
    can_edit = False
    can_delete = True
    can_view_details = True
    details_template = "admin/vpn_config_details.html"
