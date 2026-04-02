import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.scheduler.domain.event import (
    AdminNotifyEvent,
    DeletedVPNConfig,
    DeleteVPNConfigsEvent,
    SubscriptionEvent,
    UserNotifyEvent,
)
from api.scheduler.domain.stats import SubscriptionStats
from api.scheduler.enums import SubscriptionEventType
from api.scheduler.schemas import DeletedVPNConfigSchema
from api.subscription.models import DEVICE_LIMITS, Subscription
from api.users.models import User
from api.vpn.models import VPNConfig


class SubscriptionScheduler:
    """Сервис проверки подписок пользователей.

    Отвечает за:
    - анализ состояния подписок пользователей
    - применение бизнес-правил (истечение, лимиты и т.д.)
    - формирование списка событий для внешних систем (бот, сервисы)

    Сервис не выполняет побочные действия напрямую (например, отправку уведомлений
    или удаление файлов), а только генерирует события, которые должны быть
    обработаны другими компонентами системы.
    """

    async def _process_user(
        self, session: AsyncSession, user: User
    ) -> tuple[SubscriptionStats, list[type[SubscriptionEvent]]]:
        """Обрабатывает подписку конкретного пользователя и собирает статистику.

        Метод проверяет текущую подписку пользователя и выполняет следующие действия:
        1. Если подписка истекла — вызывает `_handle_expired`.
        2. Если подписка скоро истечет — вызывает `_handle_expiring_soon`.
        3. Проверяет превышение лимита VPN-конфигов для пользователя через
           `_handle_unlimited_overuse`.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: Статистика по пользователю с ключами:
                - "expired": количество истёкших подписок
                - "notified": количество отправленных уведомлений
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        stats = SubscriptionStats()
        events: list[type[SubscriptionEvent]] = []

        sub = user.current_subscription
        if not sub:
            return stats, events

        if sub.is_expired():
            s, e = await self._handle_expired(session, user, sub)
            stats.add(s)
            events.extend(e)
        else:
            s, e = await self._handle_expiring_soon(user, sub)
            stats.add(s)
            events.extend(e)

        s, e = await self._handle_unlimited_overuse(session, user)
        stats.add(s)
        events.extend(e)

        return stats, events

    async def _handle_expired(
        self, session: AsyncSession, user: User, sub: Subscription
    ) -> tuple[SubscriptionStats, list[type[SubscriptionEvent]]]:
        """Обрабатывает истёкшую подписку пользователя.

        Если подписка активна, деактивирует её и отправляет уведомление пользователю.
        Если подписка закончилась более чем на один день назад, удаляет все VPN-конфиги
        пользователя и уведомляет администраторов.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.
            sub (Subscription): Экземпляр подписки пользователя.

        Returns
            Dict[str, int]: Статистика по обработке с ключами:
                - "expired": количество истёкших подписок (0 или 1)
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        stats = SubscriptionStats()
        events: list[type[SubscriptionEvent]] = []

        if sub.is_active:
            sub.is_active = False
            stats.expired += 1

            events.append(
                UserNotifyEvent(
                    type=SubscriptionEventType.USER_NOTIFY,
                    user_id=user.telegram_id,
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    active_sbs=bool(user.current_subscription.is_active),
                    message="Подписка истекла",
                    subscription_type=(
                        user.current_subscription.type.value.upper()
                        if user.current_subscription
                        else "UNKNOWN"
                    ),
                    remaining_days=user.current_subscription.remaining_days(),
                )
            )

        if sub.end_date:
            delta = datetime.datetime.now(datetime.UTC) - sub.end_date

            if delta.days >= 1:
                deleted_configs = await self._delete_configs(
                    session, user, user.vpn_configs
                )

                stats.configs_deleted += len(deleted_configs)

                if deleted_configs:
                    files = [
                        DeletedVPNConfigSchema(file_name=c.file_name, pub_key=c.pub_key)
                        for c in deleted_configs
                    ]
                    events.append(
                        DeleteVPNConfigsEvent(
                            type=SubscriptionEventType.DELETE_VPN_CONFIGS,
                            user_id=user.telegram_id,
                            username=user.username or "undefined",
                            first_name=user.first_name or "undefined",
                            last_name=user.last_name or "undefined",
                            configs=files,
                        )
                    )

                    # events.append(
                    #     DeleteProxyEvent(
                    #         type=SubscriptionEventType.DELETE_PROXY,
                    #         user_id=user.telegram_id,
                    #     )
                    # )
                    for file in files:
                        events.append(
                            AdminNotifyEvent(
                                type=SubscriptionEventType.ADMIN_NOTIFY,
                                user_id=user.telegram_id,
                                username=user.username or "undefined",
                                first_name=user.first_name or "undefined",
                                last_name=user.last_name or "undefined",
                                message=(
                                    f"⚠️ Удалён VPN-конфиг\n"
                                    f"👤 Пользователь: @{user.username or '—'} (ID: {user.telegram_id})\n"
                                    f"📄 Файл: {file}\n"
                                    f"⏳ Причина: истекла подписка"
                                ),
                            )
                        )

        return stats, events

    async def _handle_expiring_soon(
        self, user: User, sub: Subscription
    ) -> tuple[SubscriptionStats, list[type[SubscriptionEvent]]]:
        """Обрабатывает подписку, которая скоро истечет, и уведомляет пользователя.

        Если до окончания подписки осталось 3 дня или меньше, отправляется
        уведомление пользователю через бот.

        Args:
            user (User): Экземпляр пользователя.
            sub (Subscription): Экземпляр подписки пользователя.

        Returns
            SubscriptionStats: Статистика по обработке с ключами:
                - "expired": всегда 0
                - "notified": количество отправленных уведомлений (0 или 1)
                - "configs_deleted": всегда 0

        """
        stats = SubscriptionStats()
        events: list[type[SubscriptionEvent]] = []

        remaining = sub.remaining_days()

        if remaining is not None and remaining <= 3:
            events.append(
                UserNotifyEvent(
                    type=SubscriptionEventType.USER_NOTIFY,
                    user_id=user.telegram_id,
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    message=f"Осталось {remaining} дней подписки",
                    subscription_type=(
                        user.current_subscription.type.value.upper()
                        if user.current_subscription
                        else "UNKNOWN"
                    ),
                    remaining_days=user.current_subscription.remaining_days(),
                    active_sbs=bool(user.current_subscription.is_active),
                )
            )

        return stats, events

    async def _handle_unlimited_overuse(
        self, session: AsyncSession, user: User
    ) -> tuple[SubscriptionStats, list[type[SubscriptionEvent]]]:
        """Обрабатывает превышение лимита VPN-конфигов для пользователя.

        Если количество VPN-конфигов пользователя превышает допустимый лимит
        для текущей подписки, избыточные конфиги удаляются и администраторы
        уведомляются об удалении.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: Статистика по обработке с ключами:
                - "expired": всегда 0
                - "notified": количество отправленных уведомлений администраторам (0 или >0)
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        stats = SubscriptionStats()
        events: list[type[SubscriptionEvent]] = []

        sub = user.current_subscription
        if not sub or not sub.is_active:
            return stats, events

        limit = DEVICE_LIMITS.get(sub.type) or 0
        if limit <= 0:
            return stats, events

        if len(user.vpn_configs) > limit:
            extra_cfgs = user.vpn_configs[limit:]

            deleted_configs = await self._delete_configs(session, user, extra_cfgs)

            stats.configs_deleted += len(deleted_configs)
            files = [c.file_name for c in deleted_configs]
            events.append(
                DeleteVPNConfigsEvent(
                    type=SubscriptionEventType.DELETE_VPN_CONFIGS,
                    user_id=user.telegram_id,
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    configs=files,
                )
            )
            for file in files:
                events.append(
                    AdminNotifyEvent(
                        type=SubscriptionEventType.ADMIN_NOTIFY,
                        user_id=user.telegram_id,
                        message=f"Произошло удаление конфиг файла {file} превышающий лимиты у {user.telegram_id} (@{user.username})",
                    )
                )

        return stats, events

    async def _delete_configs(
        self, session: AsyncSession, user: User, configs: list[VPNConfig]
    ) -> list[DeletedVPNConfig]:
        deleted: list[DeletedVPNConfig] = []

        for cfg in configs:
            deleted.append(
                DeletedVPNConfig(file_name=cfg.file_name, pub_key=cfg.pub_key)
            )

            await session.delete(cfg)

        return deleted

    async def check_all_subscriptions(
        self, session: AsyncSession
    ) -> tuple[SubscriptionStats, list[type[SubscriptionEvent]]]:
        """Проверяет все подписки пользователей и собирает статистику.

        Метод выполняет выборку всех пользователей с подгрузкой их подписок,
        роли и VPN-конфигов. Для каждого пользователя вызывается внутренний
        метод `_process_user`, который возвращает статистику по истёкшим
        подпискам, уведомлениям и удалённым конфигам.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.

        Returns
            SubscriptionStats: Статистика по всем пользователям. Ключи включают:
                - "checked": количество обработанных пользователей
                - "expired": количество истёкших подписок
                - "notified": количество отправленных уведомлений
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        result = await session.execute(
            select(User).options(
                selectinload(User.subscriptions),
                selectinload(User.role),
                selectinload(User.vpn_configs),
            )
        )

        users = result.scalars().all()

        stats = SubscriptionStats()
        events: list[type[SubscriptionEvent]] = []

        for user in users:
            stats.checked += 1

            s, e = await self._process_user(session, user)

            stats.add(s)
            events.extend(e)

        await session.commit()

        return stats, events
