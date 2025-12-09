import datetime
from pathlib import Path

from aiogram import Bot
from app_error.base_error import AppError
from loguru._logger import Logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.admin.enums import FilterTypeEnum
from bot.app_error.base_error import UserNotFoundError
from bot.config import settings_bot
from bot.database import connection
from bot.subscription.dao import SubscriptionDAO
from bot.subscription.enums import ToggleSubscriptionMode
from bot.subscription.models import DEVICE_LIMITS, SubscriptionType
from bot.users.dao import UserDAO
from bot.users.models import User
from bot.users.schemas import SUserOut, SUserTelegramID
from bot.users.services import UserService
from bot.utils.start_stop_bot import send_to_admins
from bot.vpn.router import ssh_lock
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG

m_subscription_local = settings_bot.messages.modes.subscription


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    key_path = Path().home() / ".ssh" / "test_vpn"

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
        """Активирует пробный период подписки."""
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
        """Активирует платную подписку после подтверждения оплаты."""
        schema_user = SUserTelegramID(telegram_id=user_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user
        )
        if not user_model:
            raise UserNotFoundError(tg_id=user_id)
        if premium:
            sub_type = SubscriptionType.PREMIUM
        else:
            sub_type = SubscriptionType.STANDARD
        check = next(
            (
                sbscr
                for sbscr in user_model.subscriptions
                if sbscr.is_active and sub_type == sbscr.type
            ),
            None,
        )
        if user_model and check:
            check.extend(months=months)
            if user_model.role.name == FilterTypeEnum.FOUNDER:
                check.type = SubscriptionType.PREMIUM
            else:
                check.type = sub_type
            await session.commit()
            return await UserService.get_user_schema(user=user_model)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months, sub_type=sub_type
        )
        await session.refresh(
            user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
        )
        return await UserService.get_user_schema(user=user_model)

    @connection()
    async def check_all_subscriptions(self, session: AsyncSession) -> dict[str, int]:
        """Проверяет все подписки, отправляет уведомления и удаляет просроченные конфиги.

        Returns
            dict[str, int]: Статистика проверки:
                {
                    "checked": количество пользователей,
                    "expired": количество истекших подписок,
                    "notified": количество отправленных уведомлений,
                    "configs_deleted": количество удалённых конфигов,
                }

        """
        result = await session.execute(
            select(User).options(
                selectinload(User.subscriptions),
                selectinload(User.role),
                selectinload(User.vpn_configs),
            )
        )
        users = result.scalars().all()

        now = datetime.datetime.now(datetime.UTC)
        stats = {
            "checked": 0,
            "expired": 0,
            "notified": 0,
            "configs_deleted": 0,
        }
        for user in users:
            stats["checked"] += 1
            sub = user.current_subscription
            if not sub:
                continue

            if sub.is_expired():
                if sub.is_active:
                    sub.is_active = False
                    await session.commit()
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=m_subscription_local.expire_subscription.now.format(
                            type_subscription=sub.type.value.upper(),
                        ),
                    )
                    await send_to_admins(
                        bot=self.bot,
                        message_text=m_subscription_local.expire_subscription.admin_stats.format(
                            tg_id=user.telegram_id,
                            username=user.username or "-",
                            first_name=user.first_name or "-",
                            last_name=user.last_name or "-",
                        ),
                    )
                    stats["expired"] += 1
                    stats["notified"] += 1
                if sub.end_date and (now - sub.end_date).days >= 1:
                    await self._delete_user_configs(session=session, user=user)
                    stats["configs_deleted"] += 1
            else:
                remaining = sub.remaining_days()
                if remaining is not None and remaining <= 3:
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=m_subscription_local.expire_subscription.soon.format(
                            remaining=remaining,
                            type_subscription=sub.type.value.upper(),
                        ),
                    )
                    stats["notified"] += 1
            await self._delete_unlimit_configs(session=session, user=user)

        return stats

    @connection()
    async def _delete_user_configs(self, session: AsyncSession, user: User) -> None:
        """Удаляет VPN-конфиги пользователя из БД."""
        if not user.vpn_configs:
            return
        async with ssh_lock:
            async with AsyncSSHClientWG(
                host=settings_bot.vpn_host,
                username=settings_bot.vpn_username,
                key_filename=self.key_path.as_posix(),
            ) as ssh_client:
                try:
                    for cfg in user.vpn_configs:
                        await ssh_client.full_delete_user(public_key=cfg.pub_key)
                        await session.delete(cfg)
                        await session.commit()
                except AmneziaError as e:
                    self.logger.error(str(e))
                    raise
        await self.bot.send_message(
            chat_id=user.telegram_id,
            text="Ваши VPN-конфиги были удалены после окончания подписки.",
        )

    @connection()
    async def _delete_unlimit_configs(self, session: AsyncSession, user: User) -> None:
        """Удаляет VPN-конфиги пользователя из БД когда у него их больше чем можно."""
        # TODO Корректно этот метод проработать , убрать type ignore
        if not user.vpn_configs and not user.current_subscription.is_active:  # type: ignore [union-attr]
            return

        limits = DEVICE_LIMITS.get(user.current_subscription.type) or 0  # type: ignore [union-attr]
        len_configs = len(user.vpn_configs)
        async with ssh_lock:
            async with AsyncSSHClientWG(
                host=settings_bot.vpn_host,
                username=settings_bot.vpn_username,
                key_filename=self.key_path.as_posix(),
            ) as ssh_client:
                try:
                    for cfg in user.vpn_configs[: (len_configs - limits)]:
                        await ssh_client.full_delete_user(public_key=cfg.pub_key)
                        await session.delete(cfg)
                        await session.commit()
                        await self.bot.send_message(
                            chat_id=user.telegram_id,
                            text=f"Ваши VPN-конфиг {cfg.file_name} превышающий лимит был удален после окончания подписки.",
                        )
                except AmneziaError as e:
                    self.logger.error(str(e))
                    raise


if __name__ == "__main__":
    print(
        m_subscription_local.expire_subscription.admin_stats.format(
            tg_id=123,
            username="user.username or ",
            first_name="sdfsdf",
            last_name="sdfsgs",
        )
    )
