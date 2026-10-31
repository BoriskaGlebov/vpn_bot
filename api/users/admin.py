from loguru import logger
from markupsafe import Markup
from sqladmin import ModelView, action, expose
from sqladmin.filters import BooleanFilter, ForeignKeyFilter
from sqladmin.templating import _TemplateResponse
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from api.admin.badges import ROLE_BADGE_COLORS, SUBSCRIPTION_BADGE_COLORS, badge
from api.app_error.base_error import (
    BotChannelUnavailableError,
    UserVPNRevokeIncompleteError,
    VPNRevokeFailedError,
)
from api.bot_channel.dependencies import get_bot_channel_client
from api.core.database import async_session
from api.promo.models import PromoCodeUsage
from api.referrals.models import Referral
from api.users.filters import SubscriptionSegmentFilter
from api.users.models import Role, User
from api.users.schemas import SVPNConfigOut


def _parse_pks(raw: str) -> list[int]:
    """Разбирает `pks` из query/form (строка `"1,2,3"`) в список ID пользователей.

    SQLAdmin передаёт отмеченные в списке строки именно так (см.
    `sqladmin.action` и `sqladmin/statics/js/main.js`) — незначимые/пустые
    токены (пустая строка при отсутствии выбора) отбрасываются молча, а не
    падают с `ValueError`.
    """
    return [int(pk) for pk in raw.split(",") if pk.strip().isdigit()]


def format_role(obj: User, name: str) -> Markup:
    """Возвращает роль пользователя цветным бейджем."""
    if not obj.role:
        return Markup("-")
    return badge(obj.role.name, ROLE_BADGE_COLORS.get(obj.role.name, "secondary"))


def format_current_subscription(obj: User, name: str) -> Markup:
    """Форматирует текущую подписку пользователя цветным бейджем."""
    sub = obj.current_subscription
    if not sub or not sub.type:
        return Markup('<span class="text-muted">-</span>')
    color = SUBSCRIPTION_BADGE_COLORS.get(sub.type.value, "secondary")
    until = sub.end_date.strftime("%Y-%m-%d") if sub.end_date else "∞"
    return Markup(f"{badge(sub.type.name, color)} до {until}")


def format_files_count(obj: User, name: str) -> int:
    """Возвращает количество VPN конфигов пользователя."""
    return len(obj.vpn_configs) if obj.vpn_configs else 0


def format_payments_count(obj: User, name: str) -> int:
    """Возвращает количество произведенных оплат."""
    return len(obj.payments) if obj.payments else 0


class UserAdmin(ModelView, model=User):
    """Админка для управления пользователями.

    В этой админке:
    - Редактируются только поля пользователя;
    - Связанные объекты (подписки, VPN конфиги) только для просмотра.
    """

    icon = "fa-solid fa-users"
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
        "payments_count",
    ]
    column_sortable_list = [
        "id",
        "telegram_id",
        "username",
        "vpn_files_count",
    ]
    details_template = "admin/user_details.html"
    column_searchable_list = ["username", "first_name", "last_name", "telegram_id"]
    column_filters = [
        BooleanFilter(User.has_used_trial, title="Использовал триал"),
        ForeignKeyFilter(User.role_id, Role.name, title="Роль"),
        SubscriptionSegmentFilter(),
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
        "role": format_role,  # type: ignore[misc, dict-item]
        "current_subscription": format_current_subscription,  # type: ignore[misc, dict-item]
        "vpn_files_count": format_files_count,  # type: ignore[misc, dict-item]
        "payments_count": format_payments_count,  # type: ignore[misc, dict-item]
        User.username: lambda m, a: (m.username or "-")[:10],  # type: ignore[misc, attr-defined]
    }  # type: ignore[misc, assignment]
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

    def _with_eager_options(self, stmt: Select[tuple[User]]) -> Select[tuple[User]]:
        """Добавляет к запросу предзагрузку связанных сущностей пользователя.

        Каждый запрос sqladmin для списка/деталей открывает и закрывает
        собственную короткоживущую сессию (``ModelView._run_query``), поэтому
        всё, что читает кастомный шаблон, должно быть eager-loaded здесь —
        иначе обращение к связи после закрытия сессии падает с
        ``DetachedInstanceError``. Предзагружаются:
            - payments, role, vpn_configs, subscriptions;
            - invited_users/invited_by вместе с вложенными
              invited/inviter (реферальный блок в user_details.html);
            - promo_usages вместе с promo_code (блок промокодов в
              user_details.html).

        Returns
            Select: тот же запрос с настроенной предзагрузкой.

        """
        return stmt.options(
            selectinload(User.payments),
            selectinload(User.role),
            selectinload(User.vpn_configs),
            selectinload(User.subscriptions),
            selectinload(User.invited_users).selectinload(Referral.invited),
            selectinload(User.invited_by).selectinload(Referral.inviter),
            selectinload(User.promo_usages).selectinload(PromoCodeUsage.promo_code),
        )

    def list_query(self, request: Request) -> Select[tuple[User]]:
        """Запрос для списка пользователей (все строки, без фильтра по pk)."""
        return self._with_eager_options(select(User))

    def details_query(self, request: Request) -> Select[tuple[User]]:
        """Запрос для страницы деталей — конкретный пользователь по pk из URL.

        Важно: без ``self._stmt_by_identifier(...)`` запрос вернёт все строки
        таблицы, и sqladmin возьмёт первую попавшуюся (``rows[0]``) — то есть
        всегда одного и того же пользователя независимо от pk в адресе.
        """
        stmt = self._stmt_by_identifier(request.path_params["pk"])
        return self._with_eager_options(stmt)

    async def on_model_delete(self, model: User, request: Request) -> None:
        """Отзывает доступ всех VPN-конфигов пользователя перед удалением записи.

        Вызывается SQLAdmin до `session.delete`/`commit` (см. `sqladmin._queries.
        Query._delete_async`) — поднятое здесь исключение останавливает
        удаление до того, как каскад (`cascade="all, delete-orphan"`) снесёт
        vpn_configs вместе с pub_key/config_ids, по которым доступ можно
        найти и отозвать (см. #246).

        Политика при частичном сбое — безопасная: пробуем отозвать КАЖДЫЙ
        конфиг (не останавливаемся на первой ошибке), а если хоть один не
        подтверждён — удаление пользователя прерывается целиком, в ошибке
        перечислены оставшиеся конфиги. Частично удалённый пользователь
        (часть доступов отозвана, часть — нет, а запись исчезла) было бы
        сложнее распутать, чем не удалить вовсе. Конфиги, что уже отозваны,
        повторный проход (повторная попытка удаления) не ломает — бот
        вернёт `NOT_FOUND`.

        `model.vpn_configs` подгружен автоматически (`User.vpn_configs`
        объявлена с `lazy="selectin"` на уровне маппера).

        Args:
            model: Удаляемый пользователь.
            request: Текущий HTTP-запрос SQLAdmin (не используется).

        Raises
            UserVPNRevokeIncompleteError: Хотя бы один конфиг не подтвердил
                отзыв доступа — удаление прервано.

        """
        client = get_bot_channel_client()
        failed_configs: list[str] = []
        for config in model.vpn_configs:
            config_out = SVPNConfigOut.model_validate(config)
            try:
                await client.revoke_config(model.telegram_id, config_out)
            except (BotChannelUnavailableError, VPNRevokeFailedError):
                failed_configs.append(f"{config.file_name} (нода: {config.node_name})")

        if failed_configs:
            logger.error(
                "Админка: удаление пользователя {} (id={}) прервано — не "
                "отозваны конфиги: {}",
                model.username,
                model.id,
                failed_configs,
            )
            raise UserVPNRevokeIncompleteError(model.id, model.username, failed_configs)

        logger.info(
            "Админка: удаление пользователя {} (id={}) — все {} VPN-конфигов отозваны",
            model.username,
            model.id,
            len(model.vpn_configs),
        )

    async def _broadcast_form_context(
        self, request: Request, pks: list[int], **extra: object
    ) -> dict[str, object]:
        """Собирает контекст формы рассылки: число получателей среди `pks`.

        Число телеграм ID считается запросом к БД, а не `len(pks)` — среди
        отмеченных строк могут попасться совпадения/устаревшие pk, и админ
        должен увидеть реальное число получателей ДО отправки, а не только
        постфактум в отчёте бота.
        """
        async with async_session() as session:
            recipients = (
                await session.scalars(select(User.telegram_id).where(User.id.in_(pks)))
            ).all()

        return {
            "pks": ",".join(str(pk) for pk in pks),
            "recipients_count": len(recipients),
            "send_url": str(
                request.url_for(f"admin:view-{self.identity}-send_broadcast")
            ),
            "list_url": str(request.url_for("admin:list", identity=self.identity)),
            **extra,
        }

    @action(
        name="send_broadcast",
        label="Отправить рассылку",
        add_in_detail=False,
        include_in_schema=False,
    )
    async def send_broadcast_form(self, request: Request) -> _TemplateResponse:
        """Открывает форму рассылки для отмеченных в списке пользователей.

        SQLAdmin передаёт выбранные pk строкой через query-параметр `pks`
        (см. `sqladmin.action`).
        """
        pks = _parse_pks(request.query_params.get("pks", ""))
        context = await self._broadcast_form_context(request, pks)
        return await self.templates.TemplateResponse(
            request, "admin/broadcast_form.html", context
        )

    @expose("/broadcast/send", methods=["POST"], include_in_schema=False)
    async def send_broadcast(self, request: Request) -> _TemplateResponse:
        """Отправляет текст рассылки боту для отмеченных pk пользователей.

        Доставка асинхронна — этот запрос только подтверждает приём команды
        ботом (`BotChannelClient.send_broadcast`, канал api→bot); итог рассылки
        (сколько доставлено) бот присылает в админ-чат отдельным сообщением.
        """
        form = await request.form()
        pks = _parse_pks(str(form.get("pks", "")))
        text = str(form.get("text", "")).strip()

        async with async_session() as session:
            recipients = (
                await session.scalars(select(User.telegram_id).where(User.id.in_(pks)))
            ).all()

        if not recipients or not text:
            error = (
                "Текст рассылки не может быть пустым."
                if not text
                else "Среди отмеченных пользователей нет получателей."
            )
            context = await self._broadcast_form_context(
                request, pks, error=error, text=text
            )
            return await self.templates.TemplateResponse(
                request, "admin/broadcast_form.html", context
            )

        accepted = await get_bot_channel_client().send_broadcast(text, list(recipients))
        logger.info(
            "Админка: запущена рассылка по {} отмеченным пользователям", accepted
        )
        return await self.templates.TemplateResponse(
            request,
            "admin/broadcast_sent.html",
            {
                "recipients_count": accepted,
                "list_url": str(request.url_for("admin:list", identity=self.identity)),
            },
        )


def format_users_count(obj: Role, name: str) -> int:
    """Возвращает количество пользователей, связанных с ролью."""
    return len(obj.users) if obj.users else 0


class RoleAdmin(ModelView, model=Role):
    """Админка для управления ролями пользователей."""

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
        "users_list": lambda m, a: (  # type: ignore[misc, dict-item]
            ", ".join(str(u) for u in m.users) if m.users else "-"  # type: ignore[misc, attr-defined,dict-item]
        ),
        "users_count": format_users_count,  # type: ignore[misc, dict-item]
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
    icon = "fa-solid fa-user-shield"
    form_columns = ["name", "description", "users"]
