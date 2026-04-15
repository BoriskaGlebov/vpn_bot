import datetime

from loguru import logger
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
from api.vpn.models import VPNConfig, VPNConfigStatus


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
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
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
        logger.info(f"Обработка пользователя: {user.username} (ID: {user.telegram_id})")
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        sub = user.current_subscription
        if not sub:
            logger.debug(f"Пользователь {user.username} не имеет активной подписки")
            return stats, events

        if sub.is_expired():
            logger.info(f"Подписка пользователя {user.username} истекла")
            s, e = await self._handle_expired(session, user, sub)
            stats.add(s)
            events.extend(e)
        else:
            logger.debug(
                f"Подписка пользователя {user.username} активна, проверяем сроки"
            )
            s, e = await self._handle_expiring_soon(user, sub)
            stats.add(s)
            events.extend(e)

        s, e = await self._handle_active_limit_exceeded(session, user)
        stats.add(s)
        events.extend(e)

        return stats, events

    async def _handle_expired(
        self, session: AsyncSession, user: User, sub: Subscription
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
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
        events: list[SubscriptionEvent] = []

        if sub.is_active:
            sub.is_active = False
            stats.expired += 1
            logger.info(f"Деактивирована подписка пользователя {user.username}")

            current_subscription = user.current_subscription
            events.append(
                UserNotifyEvent(
                    type=SubscriptionEventType.USER_NOTIFY,
                    user_id=user.telegram_id,
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    active_sbs=bool(
                        current_subscription.is_active
                        if current_subscription
                        else False
                    ),
                    message="Подписка истекла",
                    subscription_type=(
                        current_subscription.type.value.upper()
                        if current_subscription
                        else "UNKNOWN"
                    ),
                    remaining_days=(
                        current_subscription.remaining_days()
                        if current_subscription
                        else 0
                    ),
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
                    logger.warning(
                        f"Отмечено для удаления {len(deleted_configs)} VPN-конфигов пользователя {user.username}"
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
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
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
        events: list[SubscriptionEvent] = []

        remaining = sub.remaining_days()
        current_subscription = user.current_subscription
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
                        current_subscription.type.value.upper()
                        if current_subscription
                        else "UNKNOWN"
                    ),
                    remaining_days=(
                        current_subscription.remaining_days()
                        if current_subscription
                        else 0
                    ),
                    active_sbs=bool(
                        current_subscription.is_active
                        if current_subscription
                        else False
                    ),
                )
            )

        return stats, events

    async def _handle_active_limit_exceeded(
        self, session: AsyncSession, user: User
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
        """Контролирует превышение лимита VPN-конфигов при активной подписке.

        Если у пользователя есть активная подписка и количество конфигов превышает
        допустимый лимит, избыточные конфиги помечаются на удаление.

        Стратегия удаления — FIFO (удаляются самые старые конфиги).

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: Статистика по удалённым конфигам.
            list[SubscriptionEvent]: Список событий для обработки.

        """
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        sub = user.current_subscription
        if not sub or not sub.is_active:
            return stats, events

        limit = DEVICE_LIMITS.get(sub.type, 0)
        configs = user.vpn_configs or []

        if limit <= 0 or len(configs) <= limit:
            return stats, events

        # ✅ ВАЖНО: сортировка (детерминированность)
        sorted_configs = sorted(configs, key=lambda c: c.created_at)

        configs_to_delete = sorted_configs[limit:]
        if configs_to_delete:
            logger.warning(
                f"Пользователь {user.username} превысил лимит ({len(sorted_configs)}/{limit}). "
                f"Будет отправлено на удаление {len(configs_to_delete)} конфигов."
            )
        deleted_configs = await self._delete_configs(
            session=session,
            user=user,
            configs=configs_to_delete,
        )

        if not deleted_configs:
            return stats, events

        stats.configs_deleted += len(deleted_configs)

        files = [
            DeletedVPNConfigSchema(
                file_name=c.file_name,
                pub_key=c.pub_key,
            )
            for c in deleted_configs
        ]

        # единый формат события (как у тебя в expired)
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
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    message=(
                        f"⚠️ Удалён VPN-конфиг (превышение лимита)\n"
                        f"👤 Пользователь: @{user.username or '—'} (ID: {user.telegram_id})\n"
                        f"📄 Файл: {file.file_name}\n"
                        f"📊 Лимит: {limit}, было: {len(configs)}"
                    ),
                )
            )

        return stats, events

    async def _delete_configs(
        self, session: AsyncSession, user: User, configs: list[VPNConfig]
    ) -> list[DeletedVPNConfig]:
        deleted: list[DeletedVPNConfig] = []

        for cfg in configs:
            cfg.status = VPNConfigStatus.PENDING_DELETE
            deleted.append(
                DeletedVPNConfig(file_name=cfg.file_name, pub_key=cfg.pub_key)
            )
        return deleted

    async def check_all_subscriptions(
        self, session: AsyncSession
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
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
        logger.info("Начало проверки всех подписок пользователей")
        result = await session.execute(
            select(User).options(
                selectinload(User.subscriptions),
                selectinload(User.role),
                selectinload(User.vpn_configs),
            )
        )

        users = result.scalars().all()

        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        for user in users:
            stats.checked += 1

            s, e = await self._process_user(session, user)

            stats.add(s)
            events.extend(e)

        await session.commit()
        logger.info(
            f"Проверка завершена. Пользователей обработано: {stats.checked}, "
            f"истекших подписок: {stats.expired}, действий: {len(events)}, "
            f"конфигов удалено: {stats.configs_deleted}"
        )
        return stats, events
