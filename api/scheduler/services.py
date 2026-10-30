import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings_api
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
from api.users.dao import UserDAO
from api.users.models import User
from api.vpn.models import VPNConfig, VPNConfigStatus

REASON_SUBSCRIPTION_EXPIRED = "Истекла подписка"
REASON_DEVICE_LIMIT_EXCEEDED = "Превышен лимит устройств по тарифу"


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
        4. Деактивирует все остальные брошенные активные подписки пользователя —
           `current_subscription` отдаёт только одну, наиболее
           приоритетную запись, но активных записей у пользователя может
           оказаться несколько (унаследованные от момента до фикса создания
           подписок, см. `SubscriptionService.activate_paid_subscription`).

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: Статистика по пользователю с ключами:
                - "expired": количество истёкших подписок
                - "notified": количество отправленных уведомлений
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        # DEBUG, а не INFO: вызывается для каждого пользователя на каждом
        # ежедневном прогоне планировщика — на INFO это тонет в шуме и
        # маскирует реально значимые события (истечение, деактивация),
        # которые логируются отдельно ниже.
        logger.debug(
            f"Обработка пользователя: {user.username} (ID: {user.telegram_id})"
        )
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

        abandoned_active = [
            other
            for other in user.subscriptions
            if other is not sub and other.is_active
        ]
        for other in abandoned_active:
            if other.is_expired():
                logger.warning(
                    f"Брошенная активная подписка пользователя {user.username} "
                    f"истекла (тип {other.type}) — current_subscription её не "
                    f"показал первой, но деактивация обязательна"
                )
                s, e = await self._handle_expired(session, user, other)
                stats.add(s)
                events.extend(e)

        s, e = await self._handle_config_cleanup(session, user)
        stats.add(s)
        events.extend(e)

        s, e = await self._handle_active_limit_exceeded(session, user)
        stats.add(s)
        events.extend(e)

        # Единая точка после всех источников PENDING_DELETE выше (и после
        # любого более раннего — например, ручного перевода администратором
        # через массовое действие в админке): событие удаления строится по
        # фактическому статусу в БД, а не по тому, кто и когда его выставил.
        s, e = await self._handle_pending_delete_configs(session, user)
        stats.add(s)
        events.extend(e)

        return stats, events

    async def _handle_expired(
        self, session: AsyncSession, user: User, sub: Subscription
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
        """Деактивирует истёкшую подписку пользователя и уведомляет его.

        Удаление VPN-конфигов в этот метод не входит — см.
        `_handle_config_cleanup`. Раньше оно было здесь и запускалось на
        каждую истёкшую подписку пользователя; при двух истёкших записях
        (приоритетной и брошенной) это приводило к повторному
        удалению одних и тех же конфигов за один прогон планировщика —
        удвоенным уведомлениям и завышенной статистике. Решение о
        том, остался ли у пользователя доступ, зависит от состояния всех
        его подписок сразу, а не от одной переданной записи, поэтому оно
        вынесено на уровень `_process_user` и выполняется один раз на
        пользователя.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.
            sub (Subscription): Экземпляр подписки пользователя.

        Returns
            SubscriptionStats: Статистика по обработке с ключом "expired"
                (0 или 1); "configs_deleted" здесь всегда 0.
            list[SubscriptionEvent]: Уведомление пользователю об истечении,
                если подписка была активна.

        """
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        if sub.is_active:
            sub.is_active = False
            stats.expired += 1
            logger.info(f"Деактивирована подписка пользователя {user.username}")

            # Уведомление про ИСТЁКШУЮ подписку должно называть её тип, а не
            # тип какой-то другой записи: раньше subscription_type брался из
            # other_active ("другая активная подписка, если есть") — если
            # other_active не находился (пользователь лишился доступа
            # полностью — обычный случай), пользователь получал нелепое
            # "Ваша подписка UNKNOWN закончилась" вместо реального типа
            # (например, PREMIUM). Шаблон `now` в dialog_messages.yaml
            # описывает именно ту подписку, что закончилась, см. его текст.
            # active_sbs=False форсирует шаблон `now` (а не `soon`,
            # предназначенный для _handle_expiring_soon) — это уведомление
            # об истечении, не о скором истечении.
            events.append(
                UserNotifyEvent(
                    type=SubscriptionEventType.USER_NOTIFY,
                    user_id=user.telegram_id,
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    active_sbs=False,
                    message="Подписка истекла",
                    subscription_type=(
                        sub.type.value.upper() if sub.type else "UNKNOWN"
                    ),
                    remaining_days=0,
                )
            )

        return stats, events

    async def _handle_config_cleanup(
        self, session: AsyncSession, user: User
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
        """Удаляет все VPN-конфиги пользователя, если не осталось валидной подписки.

        Вызывается один раз за прогон на пользователя, а не на каждую
        истёкшую запись.

        Удаление откладывается на сутки после момента, когда доступ
        пропал на самом деле: пользователь не должен терять доступ
        в день истечения просто потому, что планировщик успел добежать
        до него. Момент отсчёта — самая поздняя из дат окончания среди
        подписок пользователя: именно она определяет, когда валидного
        доступа не осталось вообще, а не дата конкретной истёкшей записи.
        Бессрочные подписки (`end_date is None`) в отсчёте не участвуют:
        если все записи пользователя бессрочны, но деактивированы, точной
        даты потери доступа нет — удаление пропускается, как и раньше.

        Только помечает конфиги статусом/причиной — события для бота/админов
        строит отдельно `_handle_pending_delete_configs` (единая точка для
        ЛЮБОГО источника `PENDING_DELETE`, не только истечения подписки).

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: Не используется этим методом (всегда пустая) —
                оставлен для единообразия сигнатуры с остальными `_handle_*`.
            list[SubscriptionEvent]: Всегда пустой список.

        """
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        has_valid_subscription = any(
            not other.is_expired() for other in user.subscriptions
        )
        if has_valid_subscription:
            return stats, events

        dated_ends = [s.end_date for s in user.subscriptions if s.end_date]
        if not dated_ends:
            return stats, events

        delta = datetime.datetime.now(settings_api.core.tzinfo) - max(dated_ends)
        if delta.days < 1:
            return stats, events

        deleted_configs = await self._delete_configs(
            session, user, user.vpn_configs, reason=REASON_SUBSCRIPTION_EXPIRED
        )
        if deleted_configs:
            logger.warning(
                f"Отмечено для удаления {len(deleted_configs)} VPN-конфигов пользователя {user.username}"
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
                        if current_subscription and current_subscription.type
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

        Только помечает конфиги статусом/причиной — события для бота/админов
        строит отдельно `_handle_pending_delete_configs` (единая точка для
        ЛЮБОГО источника `PENDING_DELETE`, не только превышения лимита).

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: Не используется этим методом (всегда пустая) —
                оставлен для единообразия сигнатуры с остальными `_handle_*`.
            list[SubscriptionEvent]: Всегда пустой список.

        """
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        sub = user.current_subscription
        if not sub or not sub.is_active:
            return stats, events

        limit = DEVICE_LIMITS.get(sub.type, 0) if sub.type else 0
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
        await self._delete_configs(
            session=session,
            user=user,
            configs=configs_to_delete,
            reason=REASON_DEVICE_LIMIT_EXCEEDED,
        )

        return stats, events

    async def _handle_pending_delete_configs(
        self, session: AsyncSession, user: User
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
        """Строит события удаления по ВСЕМ конфигам пользователя в `PENDING_DELETE`.

        Единая точка, которая конвертирует персистентный статус БД в события
        для бота/админов — независимо от того, кто и когда перевёл конфиг в
        `PENDING_DELETE`: `_handle_config_cleanup` (истекла подписка),
        `_handle_active_limit_exceeded` (превышен лимит устройств) или
        администратор вручную через массовое действие в админке (сменился
        протокол, нода выведена из эксплуатации и т.п.). Раньше события
        строились только там, где статус выставлялся — конфиг, переведённый
        в `PENDING_DELETE` любым другим путём, никогда не подхватывался
        планировщиком: бот реально отзывает доступ и удаляет файл по событию
        `DeleteVPNConfigsEvent`, а не по самому статусу в БД, который он
        никогда не читает напрямую.

        Конфиг, который бот не смог удалить в прошлый прогон (нода была
        недоступна), останется `PENDING_DELETE` и попадёт сюда снова на
        следующий день — это намеренно (так же работало и раньше для
        истёкших подписок): лучше повторный алерт админам, чем забытый
        навсегда недоступный конфиг.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy (не
                используется — метод только читает уже загруженные
                `user.vpn_configs`, сигнатура единообразна с остальными
                `_handle_*`).
            user (User): Экземпляр пользователя.

        Returns
            SubscriptionStats: "configs_deleted" — количество конфигов,
                отправленных на удаление в этом прогоне.
            list[SubscriptionEvent]: `DeleteVPNConfigsEvent` + по одному
                `AdminNotifyEvent` на конфиг, либо пустой список, если
                конфигов в `PENDING_DELETE` нет.

        """
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        pending = [
            cfg
            for cfg in user.vpn_configs
            if cfg.status == VPNConfigStatus.PENDING_DELETE
        ]
        if not pending:
            return stats, events

        stats.configs_deleted += len(pending)

        files = [
            DeletedVPNConfigSchema(
                file_name=cfg.file_name,
                pub_key=cfg.pub_key,
                node_name=cfg.node_name,
                backend=cfg.backend,
                config_ids=cfg.config_ids,
            )
            for cfg in pending
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
        for cfg in pending:
            events.append(
                AdminNotifyEvent(
                    type=SubscriptionEventType.ADMIN_NOTIFY,
                    user_id=user.telegram_id,
                    username=user.username or "undefined",
                    first_name=user.first_name or "undefined",
                    last_name=user.last_name or "undefined",
                    message=(
                        f"⚠️ Удаляется VPN-конфиг\n"
                        f"👤 Пользователь: @{user.username or '—'} (ID: {user.telegram_id})\n"
                        f"📄 Файл: {cfg.file_name}\n"
                        f"⏳ Причина: {cfg.status_reason or 'не указана'}"
                    ),
                )
            )

        return stats, events

    async def _delete_configs(
        self,
        session: AsyncSession,
        user: User,
        configs: list[VPNConfig],
        reason: str,
    ) -> list[DeletedVPNConfig]:
        deleted: list[DeletedVPNConfig] = []

        for cfg in configs:
            cfg.status = VPNConfigStatus.PENDING_DELETE
            cfg.status_reason = reason
            deleted.append(
                DeletedVPNConfig(
                    file_name=cfg.file_name,
                    pub_key=cfg.pub_key,
                    node_name=cfg.node_name,
                    backend=cfg.backend,
                    config_ids=cfg.config_ids,
                )
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
        users = await UserDAO.find_all(session=session, options=UserDAO.base_options)

        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

        for user in users:
            stats.checked += 1

            s, e = await self._process_user(session, user)

            stats.add(s)
            events.extend(e)

        logger.info(
            f"Проверка завершена.\n"
            f"Пользователей обработано: {stats.checked},\n"
            f"истекших подписок: {stats.expired},\n"
            f"действий: {len(events)},\n"
            f"конфигов удалено: {stats.configs_deleted}"
        )
        return stats, events
