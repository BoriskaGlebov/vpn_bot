from config import settings_bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.dao.base import BaseDAO
from bot.subscription.models import DEVICE_LIMITS
from bot.vpn.models import VPNConfig


class VPNConfigDAO(BaseDAO[VPNConfig]):
    """DAO для работы с VPN-конфигами пользователей."""

    model = VPNConfig

    @classmethod
    async def can_add_config(cls, session: AsyncSession, user_id: int) -> bool:
        """Проверяет, может ли пользователь добавить новый VPN конфиг.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user_id (int): ID пользователя.

        Returns
            bool: True, если пользователь ещё не достиг лимита конфигов.

        """
        result = await session.execute(
            select(VPNConfig).where(VPNConfig.user_id == user_id)
        )
        configs = result.scalars().all() or []
        if configs:
            config_type = configs[0].user.subscription.type
            max_configs = DEVICE_LIMITS.get(config_type, 0)
            return bool(len(configs) < max_configs)
        return True

    @classmethod
    async def add_config(
        cls, session: AsyncSession, user_id: int, file_name: str, pub_key: str
    ) -> VPNConfig:
        """Создаёт новый VPN конфиг для пользователя.

        Проверяет лимит конфигов, добавляет запись в базу и возвращает объект.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user_id (int): ID пользователя.
            file_name (str): Название файла конфигурации.
            pub_key (str): Публичный ключ пользователя.

        Raises
            ValueError: Если пользователь достиг лимита конфигов.

        Returns
            VPNConfig: Созданный объект VPN-конфига.

        """
        if not await cls.can_add_config(session=session, user_id=user_id):
            raise ValueError(
                f"Пользователь {user_id} достиг лимита {settings_bot.MAX_CONFIGS_PER_USER} конфигов"
            )

        config = VPNConfig(user_id=user_id, file_name=file_name, pub_key=pub_key)
        session.add(config)
        await session.commit()
        await session.refresh(config)
        return config
