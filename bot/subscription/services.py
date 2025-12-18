import datetime
from dataclasses import dataclass

from aiogram import Bot
from loguru._logger import Logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.admin.enums import FilterTypeEnum
from bot.app_error.base_error import AppError, UserNotFoundError
from bot.config import settings_bot
from bot.database import connection
from bot.subscription.dao import SubscriptionDAO
from bot.subscription.enums import ToggleSubscriptionMode
from bot.subscription.models import DEVICE_LIMITS, Subscription, SubscriptionType
from bot.users.dao import UserDAO
from bot.users.models import User
from bot.users.schemas import SUserOut, SUserTelegramID
from bot.users.services import UserService
from bot.utils.start_stop_bot import send_to_admins
from bot.vpn.models import VPNConfig
from bot.vpn.router import ssh_lock
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG

m_subscription_local = settings_bot.messages.modes.subscription


@dataclass
class SubscriptionStats:
    """Агрегатор статистики проверки подписок.

    Класс используется для накопления и агрегации статистики как на уровне
    одного пользователя, так и для итоговой статистики по всем пользователям.

    Attributes
        checked: Количество обработанных пользователей.
        expired: Количество подписок, переведённых в истёкшие.
        notified: Количество отправленных уведомлений (пользователям и администраторам).
        configs_deleted: Количество удалённых VPN-конфигов.

    """

    checked: int = 0
    expired: int = 0
    notified: int = 0
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
        self.expired += other.expired
        self.notified += other.notified
        self.configs_deleted += other.configs_deleted


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    def __init__(self, bot: Bot, logger: Logger) -> None:
        self.bot = bot
        self.logger = logger

    @staticmethod
    async def check_premium(
        session: AsyncSession, tg_id: int
    ) -> tuple[bool, str, bool]:
        """Проверяет, имеет ли пользователь активную премиум-подписку.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.

        Returns
            tuple[bool, str, bool]: Кортеж из трёх значений:
                - bool: True, если у пользователя премиум-подписка, иначе False.
                - str: Роль пользователя (например, "founder", "user" и т.д.).
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
        if premium and premium.value == ToggleSubscriptionMode.PREMIUM:
            return True, founder.name, is_active_sbscr
        else:
            return False, founder.name, is_active_sbscr

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, user_id: int, days: int
    ) -> None:
        """Активирует пробный период подписки для пользователя.

        Метод проверяет, есть ли у пользователя активная подписка и не использовал ли он
        пробный период ранее. Если пробный период уже использован или есть активная
        подписка, будет выброшено исключение `ValueError`.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user_id (int): Telegram ID пользователя.
            days (int): Количество дней пробного периода.

        Raises
            ValueError: Если у пользователя уже есть активная подписка или пробный
                период уже использован.

        """
        schema_user = SUserTelegramID(telegram_id=user_id)
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
                await session.commit()
                return
            if (
                user_model
                and user_model.current_subscription
                and user_model.current_subscription.is_active
            ):
                raise ValueError("Уже есть активная подписка")
            if user_model and user_model.has_used_trial:
                raise ValueError("Пробный период уже был использован")

            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=schema_user,
                days=days,
                sub_type=SubscriptionType.TRIAL,
            )
            await session.refresh(user_model)
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
            await session.commit()
            return await UserService.get_user_schema(user=user_model)
        elif user_model.role.name == FilterTypeEnum.FOUNDER:
            current_sub = user_model.current_subscription
            if current_sub is not None:
                current_sub.extend(months=months)
                current_sub.type = SubscriptionType.PREMIUM
                await session.commit()
                return await UserService.get_user_schema(user=user_model)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months, sub_type=sub_type
        )
        await session.refresh(
            user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
        )
        return await UserService.get_user_schema(user=user_model)

    async def _process_user(
        self, session: AsyncSession, user: User
    ) -> SubscriptionStats:
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

        sub = user.current_subscription
        if not sub:
            return stats

        if sub.is_expired():
            stats.add(await self._handle_expired(session, user, sub))
        else:
            stats.add(await self._handle_expiring_soon(user, sub))

        stats.add(await self._handle_unlimited_overuse(session, user))

        return stats

    async def _handle_expired(
        self, session: AsyncSession, user: User, sub: Subscription
    ) -> SubscriptionStats:
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
                - "notified": количество отправленных уведомлений (0 или 1)
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        stats = SubscriptionStats()

        if sub.is_active:
            sub.is_active = False
            stats.expired += 1

            await self.bot.send_message(
                user.telegram_id,
                m_subscription_local.expire_subscription.now.format(
                    type_subscription=sub.type.value.upper()
                ),
            )
            stats.notified += 1

        if sub.end_date:
            delta = datetime.datetime.now(datetime.UTC) - sub.end_date
            if delta.days >= 1:
                deleted = await self._delete_all_configs(session, user)
                if deleted:
                    stats.configs_deleted += deleted
                    await self._notify_admins_expired(user)

        return stats

    async def _handle_expiring_soon(
        self, user: User, sub: Subscription
    ) -> SubscriptionStats:
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

        remaining = sub.remaining_days()
        if remaining is not None and remaining <= 3:
            await self.bot.send_message(
                user.telegram_id,
                m_subscription_local.expire_subscription.soon.format(
                    remaining=remaining,
                    type_subscription=sub.type.value.upper(),
                ),
            )
            stats.notified += 1

        return stats

    async def _handle_unlimited_overuse(
        self, session: AsyncSession, user: User
    ) -> SubscriptionStats:
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

        sub = user.current_subscription
        if not sub or not sub.is_active:
            return stats

        limit = DEVICE_LIMITS.get(sub.type) or 0
        if limit <= 0:
            return stats
        elif len(user.vpn_configs) >= limit:
            extra_cfgs = user.vpn_configs[: len(user.vpn_configs) - limit]

            if not extra_cfgs:
                return stats

            deleted = await self._delete_configs(session, user, extra_cfgs)
            if deleted:
                stats.configs_deleted += deleted
                await self._notify_admins_expired(user)

        return stats

    async def _delete_configs(
        self, session: AsyncSession, user: User, configs: list[VPNConfig]
    ) -> int:
        """Удаляет указанные VPN-конфиги пользователя и уведомляет его.

        Метод подключается к удалённому серверу через SSH, удаляет конфиги
        пользователя и удаляет их записи из базы данных. После успешного
        удаления каждого конфига отправляется уведомление пользователю через бот.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.
            configs (List[VPNConfig]): Список VPN-конфигов для удаления.

        Raises
            AmneziaError: В случае ошибки удаления через SSH.

        Returns
            int: Количество успешно удалённых VPN-конфигов.

        """
        if not configs:
            return 0

        deleted_count = 0

        async with ssh_lock:
            async with AsyncSSHClientWG(
                host=settings_bot.vpn_host,
                username=settings_bot.vpn_username,
            ) as ssh_client:
                for cfg in configs:
                    try:
                        await ssh_client.full_delete_user(public_key=cfg.pub_key)
                        await session.delete(cfg)
                        deleted_count += 1

                        await self.bot.send_message(
                            user.telegram_id,
                            m_subscription_local.expire_subscription.delete_unlimit_configs_user.format(
                                file_name=cfg.file_name,
                            ),
                        )

                    except AmneziaError as e:
                        self.logger.error(f"SSH deletion error: {e}")
                        raise

        return deleted_count

    async def _delete_all_configs(self, session: AsyncSession, user: User) -> int:
        """Удаляет все VPN-конфиги пользователя.

        Вызывает внутренний метод `_delete_configs` для удаления всех конфигов
        пользователя из базы данных.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Экземпляр пользователя.

        Returns
            int: Количество удалённых VPN-конфигов.

        """
        return await self._delete_configs(session, user, user.vpn_configs)

    async def _notify_admins_expired(self, user: User) -> None:
        """Отправляет уведомление администраторам о истёкшей подписке пользователя.

        Метод формирует сообщение со статистикой пользователя и отправляет его
        всем администраторам через бот.

        Args:
            user (User): Экземпляр пользователя, чья подписка истекла.

        Returns
            None

        """
        await send_to_admins(
            bot=self.bot,
            message_text=m_subscription_local.expire_subscription.admin_stats.format(
                tg_id=user.telegram_id,
                username=f"@{user.username}" or "-",
                first_name=user.first_name or "-",
                last_name=user.last_name or "-",
            ),
        )

    @connection()
    async def check_all_subscriptions(self, session: AsyncSession) -> SubscriptionStats:
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
        for user in users:
            stats.checked += 1
            user_stats = await self._process_user(session, user)
            stats.add(user_stats)

        await session.commit()
        await send_to_admins(
            bot=self.bot,
            message_text=m_subscription_local.daily_check.format(
                checked=stats.checked or 0,
                expired=stats.expired or 0,
                notified=stats.notified or 0,
                configs_deleted=stats.configs_deleted or 0,
            ),
        )
        return stats


if __name__ == "__main__":
    print(
        m_subscription_local.expire_subscription.admin_stats.format(
            tg_id=123,
            username="user.username or ",
            first_name="sdfsdf",
            last_name="sdfsgs",
        )
    )
