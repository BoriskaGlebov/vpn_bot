from loguru import logger
from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import ForeignKeyFilter, OperationColumnFilter
from starlette.requests import Request

from api.admin.badges import VPN_CONFIG_BADGE_COLORS, VPN_CONFIG_STATUS_LABELS, badge
from api.bot_channel.dependencies import get_bot_channel_client
from api.users.models import User
from api.users.schemas import SVPNConfigOut
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

    # can_create/can_edit остаются запрещены: SQLAdmin писал бы модель
    # напрямую в БД, минуя VPNService/VPNConfigDAO.add_config — тот самый
    # слой, который отзывает/выдаёт доступ на ноде или панели 3x-ui и
    # проверяет лимит устройств. Этот слой живёт в bot/ (только bot/
    # обращается к панелям VPN) — так появилась бы запись без node_name/
    # backend/protocol/config_ids, которая уже считается устройством
    # пользователя и занимает место в лимите, но не имеет доступа.
    #
    # can_delete включено (#290/#382): on_model_delete ниже отзывает доступ
    # конфига на ноде через BotChannelClient (канал api -> bot) ДО того, как
    # SQLAdmin удалит строку — см. docstring on_model_delete.
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
