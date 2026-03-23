import datetime
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    AppError,
    TrialAlreadyUsedError,
    UserNotFoundError,
)
from api.core.database import connection
from api.core.mapper.user_mapper import UserMapper
from api.subscription.dao import SubscriptionDAO
from api.subscription.enums import SubscriptionEventType, ToggleSubscriptionMode
from api.subscription.models import DEVICE_LIMITS, Subscription, SubscriptionType
from api.users.dao import UserDAO
from api.users.models import User
from api.vpn.models import VPNConfig
from shared.enums.admin_enum import FilterTypeEnum, RoleEnum
from shared.schemas.users import SUserOut, SUserTelegramID


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    @staticmethod
    async def check_premium(
        session: AsyncSession, tg_id: int
    ) -> tuple[bool, RoleEnum, bool]:
        """Проверяет, имеет ли пользователь активную премиум-подписку.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.

        Returns
            tuple[bool, str, bool]: Кортеж из трёх значений:
                - bool: True, если у пользователя премиум-подписка, иначе False.
                - RoleEnum: Роль пользователя (например, "founder", "user" и т.д.).
                - bool: True, если подписка активна, иначе False.

        Raises
            UserNotFoundError: Если пользователь с указанным Telegram ID не найден.

        """
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=tg_id)
        )
        if not user_model:
            raise UserNotFoundError(tg_id=tg_id)
        if user_model.current_subscription is None:
            raise AppError(message="Некорректно распаковал подписку!")
        premium = user_model.current_subscription.type
        founder = user_model.role
        is_active_sbscr = bool(user_model.current_subscription.is_active)
        if premium and premium == ToggleSubscriptionMode.PREMIUM:
            return True, RoleEnum(founder.name), is_active_sbscr
        else:
            return False, RoleEnum(founder.name), is_active_sbscr

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, tg_id: int, days: int
    ) -> None:
        """Активирует пробный период подписки для пользователя.

        Метод проверяет, есть ли у пользователя активная подписка и не использовал ли он
        пробный период ранее. Если пробный период уже использован или есть активная
        подписка, будет выброшено исключение `ValueError`.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.
            days (int): Количество дней пробного периода.

        Raises
            ValueError: Если у пользователя уже есть активная подписка или пробный
                период уже использован.

        """
        schema_user = SUserTelegramID(telegram_id=tg_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user
        )
        try:
            if (
                user_model
                and user_model.current_subscription
                and user_model.current_subscription.is_active
                and not user_model.has_used_trial
            ):
                user_model.current_subscription.extend(days=days)
                user_model.has_used_trial = True
                # await session.commit()
                return
            if (
                user_model
                and user_model.current_subscription
                and user_model.current_subscription.is_active
            ):
                raise ActiveSubscriptionExistsError()
            if user_model and user_model.has_used_trial:
                raise TrialAlreadyUsedError()

            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=schema_user,
                days=days,
                sub_type=SubscriptionType.TRIAL,
            )
            await session.refresh(
                user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
            )
        except ValueError:
            raise

    @staticmethod
    async def activate_paid_subscription(
        session: AsyncSession, user_id: int, months: int, premium: bool
    ) -> SUserOut | None:
        """Активирует платную подписку после подтверждения оплаты.

        Метод проверяет наличие пользователя и активной подписки указанного типа.
        Если подписка уже активна, продлевает её. Для основателя (`FOUNDER`)
        всегда продлевается текущая подписка и устанавливается тип `PREMIUM`.
        В противном случае создается новая подписка через DAO.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user_id (int): Telegram ID пользователя.
            months (int): Количество месяцев для продления или новой подписки.
            premium (bool): Флаг, указывающий на тип подписки (`PREMIUM` или `STANDARD`).

        Returns
            Optional[SUserOut]: Объект пользователя в формате схемы, либо `None`, если
                пользователь не найден (в реальности выбрасывается `UserNotFoundError`).

        Raises
            UserNotFoundError: Если пользователь с указанным `user_id` не найден.

        """
        schema_user = SUserTelegramID(telegram_id=user_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user
        )
        if not user_model:
            raise UserNotFoundError(tg_id=user_id)
        sub_type = SubscriptionType.PREMIUM if premium else SubscriptionType.STANDARD
        active_sub = next(
            (
                sbscr
                for sbscr in user_model.subscriptions
                if sbscr.is_active and sub_type == sbscr.type
            ),
            None,
        )
        if active_sub:
            active_sub.extend(months=months)
            return await UserMapper.to_schema(user=user_model)
        elif user_model.role.name == FilterTypeEnum.FOUNDER:
            current_sub = user_model.current_subscription
            if current_sub is not None:
                current_sub.extend(months=months)
                current_sub.type = SubscriptionType.PREMIUM
                return await UserMapper.to_schema(user=user_model)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months, sub_type=sub_type
        )
        await session.refresh(
            user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
        )
        return await UserMapper.to_schema(user=user_model)


@dataclass
class BaseEvent:
    type: SubscriptionEventType


@dataclass
class UserNotifyEvent(BaseEvent):
    user_id: int
    message: str


@dataclass
class AdminNotifyEvent(BaseEvent):
    message: str
    user_id: int


@dataclass
class DeleteProxyEvent(BaseEvent):
    user_id: int


@dataclass
class DeleteVPNConfigsEvent(BaseEvent):
    user_id: int
    configs: list[str]  # или pub_keys


@dataclass
class DeletedVPNConfig:
    file_name: str
    pub_key: str


SubscriptionEvent = (
    UserNotifyEvent | AdminNotifyEvent | DeleteProxyEvent | DeleteVPNConfigsEvent
)


@dataclass
class SubscriptionStats:
    """Агрегатор статистики проверки подписок.

    Класс используется для накопления и агрегации статистики как на уровне
    одного пользователя, так и для итоговой статистики по всем пользователям.

    Attributes
        checked: Количество обработанных пользователей.
        expired: Количество подписок, переведённых в истёкшие.
        configs_deleted: Количество удалённых VPN-конфигов.

    """

    checked: int = 0
    expired: int = 0
    configs_deleted: int = 0

    def add(self, other: "SubscriptionStats") -> None:
        """Добавляет значения счётчиков из другого объекта статистики.

        Метод выполняет покомпонентное суммирование счётчиков и используется
        для агрегации статистики от отдельных обработчиков или пользователей.

        Args:
            other: Экземпляр `SubscriptionStats`, значения которого будут
                добавлены к текущему объекту.

        Returns
            None

        """

        self.checked += other.checked
        self.expired += other.expired
        self.configs_deleted += other.configs_deleted


class SubscriptionScheduler:
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
        stats = SubscriptionStats()
        events: list[SubscriptionEvent] = []

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
        deleted_configs: list[DeletedVPNConfig] = []

        if sub.is_active:
            sub.is_active = False
            stats.expired += 1

            events.append(
                UserNotifyEvent(
                    type=SubscriptionEventType.USER_NOTIFY,
                    user_id=user.telegram_id,
                    message="Подписка истекла",
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
                    events.append(
                        DeleteVPNConfigsEvent(
                            type=SubscriptionEventType.DELETE_VPN_CONFIGS,
                            user_id=user.telegram_id,
                            configs=[c.file_name for c in deleted_configs],
                        )
                    )

                events.append(
                    DeleteProxyEvent(
                        type=SubscriptionEventType.DELETE_PROXY,
                        user_id=user.telegram_id,
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

        if remaining is not None and remaining <= 3:
            events.append(
                UserNotifyEvent(
                    type=SubscriptionEventType.USER_NOTIFY,
                    user_id=user.telegram_id,
                    message=f"Осталось {remaining} дней подписки",
                )
            )

        return stats, events

    async def _handle_unlimited_overuse(
        self, session: AsyncSession, user: User
    ) -> tuple[SubscriptionStats, list[SubscriptionEvent]]:
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
        events: list[SubscriptionEvent] = []

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

            events.append(
                DeleteVPNConfigsEvent(
                    type=SubscriptionEventType.DELETE_VPN_CONFIGS,
                    user_id=user.telegram_id,
                    configs=[c.file_name for c in deleted_configs],
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

    @connection()
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

        return stats, events
