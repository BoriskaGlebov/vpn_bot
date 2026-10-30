from loguru import logger
from markupsafe import Markup
from sqladmin import ModelView, action, expose
from sqladmin.filters import (
    AllUniqueStringValuesFilter,
    ForeignKeyFilter,
    OperationColumnFilter,
    StaticValuesFilter,
)
from sqladmin.templating import _TemplateResponse
from sqlalchemy import select
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
from api.core.database import async_session
from api.users.models import User
from api.users.schemas import SVPNConfigOut
from api.vpn.dao import VPNConfigDAO
from api.vpn.models import VPNConfig, VPNConfigStatus
from shared.enums.vpn_enum import VPNBackend

# Пресеты причины перевода в PENDING_DELETE, предлагаемые админу в форме
# массового действия. "Другое" раскрывает свободный текст — список не
# пытается перечислить все возможные причины (их по определению не
# предугадать все), а закрывает самые частые, чтобы не печатать их руками
# каждый раз.
VPN_CONFIG_PENDING_DELETE_REASON_PRESETS = [
    "Истекла подписка",
    "Сменился протокол подключения",
    "Нода/сервер выведен из эксплуатации",
    "Другое",
]


def _parse_pks(raw: str) -> list[int]:
    """Разбирает `pks` из query/form (строка `"1,2,3"`) в список ID конфигов.

    SQLAdmin передаёт отмеченные в списке строки именно так (см.
    `sqladmin.action` и `sqladmin/statics/js/main.js`) — незначимые/пустые
    токены (пустая строка при отсутствии выбора) отбрасываются молча, а не
    падают с `ValueError`.
    """
    return [int(pk) for pk in raw.split(",") if pk.strip().isdigit()]


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


def format_status_reason(obj: VPNConfig, name: str) -> str:
    """Отображает причину перевода в PENDING_DELETE с безопасным дефолтом."""
    return obj.status_reason or "-"


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
        "status_reason",
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
        "status_reason": "Причина",
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
        "status_reason": format_status_reason,  # type: ignore[misc, dict-item]
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

    async def _pending_delete_form_context(
        self, request: Request, pks: list[int], **extra: object
    ) -> dict[str, object]:
        """Собирает контекст формы: отмеченные конфиги и сколько из них реально переведётся.

        "Реально переведётся" считается отдельно от `len(pks)` — среди
        отмеченных строк могут попасться уже `PENDING_DELETE`/`DELETED`
        записи (см. `VPNConfigDAO.mark_pending_delete`, которая трогает
        только `ACTIVE`), и админ должен увидеть это ДО отправки, а не
        только по итоговому числу обновлённых строк в отчёте.
        """
        async with async_session() as session:
            configs = (
                await session.scalars(select(VPNConfig).where(VPNConfig.id.in_(pks)))
            ).all()

        eligible = [c for c in configs if c.status == VPNConfigStatus.ACTIVE]
        return {
            "pks": ",".join(str(pk) for pk in pks),
            "configs": configs,
            "eligible_count": len(eligible),
            "reason_presets": VPN_CONFIG_PENDING_DELETE_REASON_PRESETS,
            "mark_url": str(
                request.url_for(f"admin:view-{self.identity}-mark_pending_delete")
            ),
            "list_url": str(request.url_for("admin:list", identity=self.identity)),
            **extra,
        }

    @action(
        name="mark_pending_delete",
        label="Пометить на удаление",
        add_in_detail=False,
        include_in_schema=False,
    )
    async def mark_pending_delete_form(self, request: Request) -> _TemplateResponse:
        """Открывает форму причины удаления для отмеченных в списке конфигов.

        SQLAdmin передаёт выбранные pk строкой через query-параметр `pks`
        (см. `sqladmin.action`).
        """
        pks = _parse_pks(request.query_params.get("pks", ""))
        context = await self._pending_delete_form_context(request, pks)
        return await self.templates.TemplateResponse(
            request, "admin/vpn_config_pending_delete_form.html", context
        )

    @expose("/pending-delete/mark", methods=["POST"], include_in_schema=False)
    async def mark_pending_delete(self, request: Request) -> _TemplateResponse:
        """Переводит отмеченные конфиги в `PENDING_DELETE` с указанной причиной.

        Доступ на нодах здесь не трогается — запись только помечается;
        реальный отзыв доступа и удаление строки выполнит планировщик при
        следующем прогоне (`bot/scheduler/services.py:_trigger_config_deletion`),
        так же, как для конфигов, помеченных автоматически по истечению
        подписки или превышению лимита устройств.
        """
        form = await request.form()
        pks = _parse_pks(str(form.get("pks", "")))
        preset = str(form.get("reason_preset", "")).strip()
        custom = str(form.get("reason_custom", "")).strip()
        reason = custom if preset == "Другое" else preset

        if not reason:
            context = await self._pending_delete_form_context(
                request, pks, error="Укажите причину удаления."
            )
            return await self.templates.TemplateResponse(
                request, "admin/vpn_config_pending_delete_form.html", context
            )

        async with async_session() as session:
            updated = await VPNConfigDAO.mark_pending_delete(
                session=session, config_ids=pks, reason=reason
            )
            await session.commit()

        logger.info(
            "Админка: {} конфигов помечено на удаление (причина: {})",
            updated,
            reason,
        )
        return await self.templates.TemplateResponse(
            request,
            "admin/vpn_config_pending_delete_done.html",
            {
                "updated_count": updated,
                "reason": reason,
                "list_url": str(request.url_for("admin:list", identity=self.identity)),
            },
        )
