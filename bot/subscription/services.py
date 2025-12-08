import datetime
from pathlib import Path

from aiogram import Bot
from loguru._logger import Logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.enums import FilterTypeEnum
from bot.app_error.base_error import UserNotFoundError
from bot.config import settings_bot
from bot.database import connection
from bot.subscription.dao import SubscriptionDAO
from bot.subscription.enums import ToggleSubscriptionMode
from bot.subscription.models import SubscriptionType
from bot.users.dao import UserDAO
from bot.users.models import User
from bot.users.schemas import SUserOut, SUserTelegramID
from bot.vpn.router import ssh_lock
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


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
        premium = user_model.subscription.type
        founder = user_model.role
        is_active_sbscr = user_model.subscription.is_active
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
                and user_model.subscription.is_active
                and not user_model.has_used_trial
            ):
                user_model.subscription.extend(days=days)
                user_model.has_used_trial = True
                await session.commit()
                return
            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=schema_user,
                days=days,
                sub_type=SubscriptionType.TRIAL,
            )
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
        if user_model and user_model.subscription.is_active:
            user_model.subscription.extend(months=months)
            if user_model.role.name == FilterTypeEnum.FOUNDER:
                user_model.subscription.type = SubscriptionType.PREMIUM
            else:
                user_model.subscription.type = sub_type
            await session.commit()
            return SUserOut.model_validate(user_model)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months, sub_type=sub_type
        )
        return SUserOut.model_validate(user_model)

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
        result = await session.execute(select(User).options())
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
            sub = user.subscription
            if not sub:
                continue

            if sub.is_expired():
                if sub.is_active:
                    sub.is_active = False
                    await session.commit()
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text="Ваша подписка закончилась 🔒. Конфиги будут удалены через день.",
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
                        text=f"⚠️ Ваша подписка истекает через {remaining} дней.",
                    )
                    stats["notified"] += 1
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
