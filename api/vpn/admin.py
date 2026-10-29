from loguru import logger
from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import (
    AllUniqueStringValuesFilter,
    ForeignKeyFilter,
    OperationColumnFilter,
    StaticValuesFilter,
)
from starlette.requests import Request

from api.admin.badges import (
    VPN_BACKEND_BADGE_COLORS,
    VPN_BACKEND_LABELS,
    VPN_CONFIG_BADGE_COLORS,
    VPN_CONFIG_STATUS_LABELS,
    VPN_PROTOCOL_LABELS,
    badge,
)
from api.bot_channel.dependencies import get_bot_channel_client
from api.users.models import User
from api.users.schemas import SVPNConfigOut
from api.vpn.models import VPNConfig, VPNConfigStatus
from shared.enums.vpn_enum import VPNBackend


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


def format_node_name(obj: VPNConfig, name: str) -> str:
    """Отображает имя ноды с безопасным дефолтом для отсутствующего значения."""
    return obj.node_name or "—"


def format_backend(obj: VPNConfig, name: str) -> Markup:
    """Форматирует бэкенд (AmneziaWG/XRay) цветным бейджем."""
    if not obj.backend:
        return badge("—", "dark")
    label = VPN_BACKEND_LABELS.get(obj.backend, obj.backend)
    color = VPN_BACKEND_BADGE_COLORS.get(obj.backend, "dark")
    return badge(label, color)


def format_protocol(obj: VPNConfig, name: str) -> str:
    """Отображает протокол(ы) конфига человекочитаемо.

    Для XRay-подписки `protocol` хранит несколько значений через запятую
    (по одному на inbound) — каждое значение подписывается отдельно.
    """
    if not obj.protocol:
        return "—"
    labels = (
        VPN_PROTOCOL_LABELS.get(p.strip(), p.strip()) for p in obj.protocol.split(",")
    )
    return ", ".join(labels)


class VPNConfigAdmin(ModelView, model=VPNConfig):
    """Административное представление модели VPNConfig."""

    name = "VPN конфиг"
    name_plural = "VPN конфиги"
    icon = "fa-solid fa-network-wired"

    # Короткий список: таблица конфигов и так широкая, поэтому file_name и
    # pub_key (малоинформативны в общем списке) остаются только на карточке
    # конфига (column_details_list + admin/vpn_config_details.html).
    column_list = [
        "id",
        "user",
        "status",
        "node_name",
        "backend",
        "protocol",
        "country",
        "created_at",
    ]

    column_details_list = [
        "id",
        "user",
        "file_name",
        "pub_key",
        "status",
        "node_name",
        "backend",
        "protocol",
        "country",
        "created_at",
    ]

    column_sortable_list = [
        "id",
        "file_name",
        "user_id",
        "status",
        "node_name",
        "backend",
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
        # Статус/бэкенд — фиксированный набор значений (Python-enum), поэтому
        # выпадающий список задаётся явно, а не через OperationColumnFilter.
        StaticValuesFilter(
            VPNConfig.status,
            values=[
                (s.value, VPN_CONFIG_STATUS_LABELS[s.value]) for s in VPNConfigStatus
            ],
            title="Статус",
        ),
        StaticValuesFilter(
            VPNConfig.backend,
            values=[(b.value, VPN_BACKEND_LABELS[b.value]) for b in VPNBackend],
            title="Бэкенд",
        ),
        # node_name не Python-enum (валидируется по settings_bot.vpn.nodes,
        # недоступному из api/, см. api/vpn/locations.py) — список строится
        # запросом DISTINCT по реальным значениям в БД.
        AllUniqueStringValuesFilter(VPNConfig.node_name, title="Нода"),
        # Contains, а не выпадающий список: XRay-подписка хранит несколько
        # значений в protocol через запятую (см. VPNConfig.protocol) —
        # и Equals, и список уникальных сырых строк для такого поля не имеют
        # смысла.
        OperationColumnFilter(VPNConfig.protocol, title="Протокол"),
    ]

    column_labels = {
        "id": "ID",
        "user": "Пользователь",
        "file_name": "Имя файла",
        "pub_key": "Public key",
        "status": "Статус",
        "node_name": "Нода",
        "backend": "Бэкенд",
        "protocol": "Протокол",
        "country": "Страна",
        "created_at": "Дата создания",
    }

    column_formatters = {
        "user": format_user,  # type: ignore[misc, dict-item]
        "pub_key": format_pub_key,  # type: ignore[misc, dict-item]
        "status": format_status,  # type: ignore[misc, dict-item]
        "node_name": format_node_name,  # type: ignore[misc, dict-item]
        "backend": format_backend,  # type: ignore[misc, dict-item]
        "protocol": format_protocol,  # type: ignore[misc, dict-item]
    }

    # create/edit запрещены: SQLAdmin писал бы модель напрямую в БД, минуя
    # слой выдачи доступа в bot/ — появилась бы запись без доступа на ноде,
    # но уже занимающая место в лимите устройств пользователя.
    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True
    details_template = "admin/vpn_config_details.html"

    async def on_model_delete(self, model: VPNConfig, request: Request) -> None:
        """Отзывает доступ конфига на ноде/панели перед удалением записи.

        Вызывается SQLAdmin до `session.delete`/`commit` (см. `sqladmin._queries.
        Query._delete_async`) — если отзыв не подтверждён, нужно поднять
        исключение: тогда SQLAdmin не выполнит сам DELETE, и запись останется
        в БД согласованной с нодой (на которой доступ ещё жив).

        `model.user` подгружен автоматически (`VPNConfig.user` объявлена с
        `lazy="selectin"` на уровне маппера), дополнительный eager loading не
        нужен.

        Args:
            model: Удаляемый конфиг.
            request: Текущий HTTP-запрос SQLAdmin (не используется).

        Raises
            BotChannelUnavailableError: Бот недоступен — проброс из
                `BotChannelClient.revoke_config`, запись не удаляется.
            VPNRevokeFailedError: Нода/панель не смогла отозвать доступ —
                проброс из `BotChannelClient.revoke_config`, запись не
                удаляется.

        """
        config_out = SVPNConfigOut.model_validate(model)
        logger.info(
            "Админка: удаление VPN-конфига {} (user_id={}) — отзываю доступ на ноде",
            model.file_name,
            model.user_id,
        )
        await get_bot_channel_client().revoke_config(model.user.telegram_id, config_out)
