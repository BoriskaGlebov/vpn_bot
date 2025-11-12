import datetime
from pathlib import Path

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.subscription.dao import SubscriptionDAO
from bot.subscription.models import SubscriptionType
from bot.users.models import User
from bot.users.schemas import SUserTelegramID
from bot.vpn.router import ssh_lock
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    key_path = Path().home() / ".ssh" / "test_vpn"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, user_id: int, days: int
    ) -> None:
        """Активирует пробный период подписки."""
        schema_user = SUserTelegramID(telegram_id=user_id)
        try:
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
        session: AsyncSession, user_id: int, months: int
    ) -> None:
        """Активирует платную подписку после подтверждения оплаты."""
        schema_user = SUserTelegramID(telegram_id=user_id)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months
        )

    @connection()
    async def check_all_subscriptions(self, session: AsyncSession) -> None:
        """Проверяет все подписки, отправляет уведомления и удаляет просроченные конфиги."""
        result = await session.execute(select(User).options())
        users = result.scalars().all()

        now = datetime.datetime.now(datetime.UTC)

        for user in users:
            sub = user.subscription
            if not sub:
                continue

            if sub.is_expired():
                # Подписка истекла
                if sub.is_active:
                    sub.is_active = False
                    await session.commit()
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text="Ваша подписка закончилась 🔒. Конфиги будут удалены через день.",
                    )
                # Проверяем, прошло ли более 1 дня после окончания
                if sub.end_date and (now - sub.end_date).days >= 1:
                    await self._delete_user_configs(session=session, user=user)
            else:
                # Подписка активна
                remaining = sub.remaining_days()
                if remaining is not None and remaining <= 3:
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=f"⚠️ Ваша подписка истекает через {remaining} дней.",
                    )

    @connection()
    async def _delete_user_configs(self, session: AsyncSession, user: User) -> None:
        """Удаляет VPN-конфиги пользователя из БД."""
        if not user.vpn_configs:
            return
        async with ssh_lock:
            async with AsyncSSHClientWG(
                host=settings_bot.VPN_HOST,
                username=settings_bot.VPN_USERNAME,
                key_filename=self.key_path.as_posix(),
            ) as ssh_client:
                try:
                    for cfg in user.vpn_configs:
                        await ssh_client.full_delete_user(public_key=cfg.pub_key)
                        await session.delete(cfg)
                        await session.commit()
                except Exception as e:
                    print(str(e))
        await self.bot.send_message(
            chat_id=user.telegram_id,
            text="Ваши VPN-конфиги были удалены после окончания подписки.",
        )
