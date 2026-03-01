from typing import Any

from sqladmin import ModelView
from sqladmin.filters import ForeignKeyFilter, OperationColumnFilter

from bot.users.models import User
from bot.vpn.models import VPNConfig


def format_user(model: VPNConfig, _: Any) -> str:
    """Форматирует отображение пользователя в списке.

    Args
        model: Экземпляр VPNConfig.
        _: Контекст SQLAdmin (не используется).

    Returns
        str: Строка формата
            "<username> (<telegram_id>)"
            или "-" если пользователь отсутствует.

    """
    if model.user is None:
        return "-"
    return f"{model.user.username} ({model.user.telegram_id})"


def format_pub_key(model: VPNConfig, _: Any) -> str:
    """Форматирует публичный ключ для отображения.

    Обрезает ключ до 25 символов для компактного вывода.

    Args
        model: Экземпляр VPNConfig.
        _: Контекст SQLAdmin (не используется).

    Returns
        str: Укороченный публичный ключ или "-".

    """
    if not model.pub_key:
        return "-"
    return f"{model.pub_key[:25]}..."


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

    column_list = [
        "id",
        "user",
        "file_name",
        "pub_key",
    ]

    column_sortable_list = [
        "id",
        "file_name",
        "user_id",
    ]

    column_searchable_list = [
        "file_name",
        "pub_key",
        "user.username",
    ]

    column_filters = [
        ForeignKeyFilter(VPNConfig.user_id, User.username, title="Пользователь"),
        OperationColumnFilter(VPNConfig.file_name),
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
    }

    column_formatters = {
        "user": format_user,
        "pub_key": format_pub_key,
    }

    can_create = True
    can_edit = False
    can_delete = True
    can_view_details = True
    details_template = "admin/vpn_config_details.html"
