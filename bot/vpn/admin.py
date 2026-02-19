from sqladmin import ModelView
from sqladmin.filters import ForeignKeyFilter, OperationColumnFilter

from bot.users.models import User
from bot.vpn.models import VPNConfig


class VPNConfigAdmin(ModelView, model=VPNConfig):
    name = "VPN конфиг"
    name_plural = "VPN конфиги"

    # таблица
    column_list = [
        "id",
        "user",
        "file_name",
        "pub_key",
    ]

    # сортировка
    column_sortable_list = [
        "id",
        "file_name",
        "user_id",
    ]

    # поиск
    column_searchable_list = [
        "file_name",
        "pub_key",
        "user.username",
    ]

    # фильтры справа
    column_filters = [
        ForeignKeyFilter(VPNConfig.user_id, User.username, title="Пользователь"),
        OperationColumnFilter(VPNConfig.file_name),
    ]

    # форма редактирования
    form_columns = [
        "user",
        "file_name",
        "pub_key",
    ]

    # подписи
    column_labels = {
        "id": "ID",
        "user": "Пользователь",
        "file_name": "Имя файла",
        "pub_key": "Public key",
    }

    # красивый вывод
    column_formatters = {
        "user": lambda m, a: (
            f"{m.user.username} ({m.user.telegram_id})" if m.user else "-"
        ),
        "pub_key": lambda m, a: (m.pub_key[:25] + "..." if m.pub_key else "-"),
    }

    # права
    can_create = True
    can_edit = False
    can_delete = True
    can_view_details = True
    details_template = "admin/vpn_config_details.html"
