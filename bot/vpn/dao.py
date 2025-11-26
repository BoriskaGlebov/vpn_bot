from sqlalchemy.ext.asyncio import AsyncSession

from bot.dao.base import BaseDAO
from bot.vpn.models import VPNConfig


class VPNConfigDAO(BaseDAO[VPNConfig]):
    """DAO для работы с VPN-конфигами пользователей."""

    model = VPNConfig

    @classmethod
    async def can_add_config(cls, session: AsyncSession, user_id: int) -> bool:
        pass

    @classmethod
    async def add_config(
        cls, session: AsyncSession, user_id: int, file_name: str, pub_key: str
    ) -> VPNConfig:
        pass
