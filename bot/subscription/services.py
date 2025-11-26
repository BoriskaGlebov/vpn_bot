from pathlib import Path

from aiogram import Bot
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import connection
from bot.users.models import User
from bot.users.schemas import SUserOut


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
        pass

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, user_id: int, days: int
    ) -> None:
        pass

    @staticmethod
    async def activate_paid_subscription(
        session: AsyncSession, user_id: int, months: int, premium: bool
    ) -> SUserOut | None:
        pass

    @connection()
    async def check_all_subscriptions(self, session: AsyncSession) -> dict[str, int]:
        pass

    @connection()
    async def _delete_user_configs(self, session: AsyncSession, user: User) -> None:
        pass
