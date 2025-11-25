from pathlib import Path

from aiogram.types import User as TGUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


class VPNService:
    """Сервис для работы с VPN-конфигами и подписками пользователей."""

    async def generate_user_config(
        self,
        session: AsyncSession,
        user: TGUser,
        ssh_client: AsyncSSHClientWG | AsyncSSHClientVPN,
    ) -> tuple[Path, str]:
        pass

    @staticmethod
    async def get_subscription_info(tg_id: int, session: AsyncSession) -> str:
        pass
