from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import ForeignKeyFilter, OperationColumnFilter

from api.admin.badges import VPN_CONFIG_BADGE_COLORS, VPN_CONFIG_STATUS_LABELS, badge
from api.users.models import User
from api.vpn.models import VPNConfig


def format_user(obj: VPNConfig, name: str) -> str:
    """Форматирует отображение пользователя в списке."""
    if obj.user is None:
        return "-"
    return f"{obj.user.username or '-'} ({obj.user.telegram_id})"


def format_pub_key(obj: VPNConfig, name: str) -> str:
    """Форматирует публичный ключ для отображения."""
    if not obj.pub_key:
        return "-"
    return f"{obj.pub_key[:25]}..."


def format_status(obj: VPNConfig, name: str) -> Markup:
    """Форматирует статус конфига цветным бейджем."""
    status = obj.status.value
    label = VPN_CONFIG_STATUS_LABELS.get(status, status)
    color = VPN_CONFIG_BADGE_COLORS.get(status, "dark")
    return badge(label, color)


class VPNConfigAdmin(ModelView, model=VPNConfig):
    """Административное представление модели VPNConfig."""

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

    # Создание и удаление запрещены по одной и той же причине: SQLAdmin
    # пишет/удаляет модель напрямую в БД, минуя VPNService — тот самый слой,
    # который отзывает/выдаёт доступ на ноде или панели 3x-ui и проверяет
    # лимит устройств. Этот слой живёт в bot/ (только bot/ обращается к
    # панелям VPN), поэтому админка не может вызвать его напрямую — пока не
    # появится путь между сервисами, обе операции запрещены целиком.
    #
    # can_delete (см. #246): запись исчезает, а клиент на панели/пир в
    # awg0.conf остаётся включённым — доступ без записи, по которой его
    # можно найти. Правильный путь — VPNService.delete_user_config
    # (bot/vpn/services.py, уже используется в bot/subscription/router.py):
    # отзывает доступ на ноде и только потом удаляет запись, различая
    # "не найден" и "ошибка связи".
    #
    # can_create (см. #272): наоборот — запись появляется без доступа.
    # node_name/backend/protocol/config_ids остаются пустыми, при этом
    # запись уже считается устройством пользователя и приближает его к
    # лимиту, а проверка лимита при создании не выполняется (она встроена
    # в VPNConfigDAO.add_config, SQLAdmin его не вызывает).
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    details_template = "admin/vpn_config_details.html"
