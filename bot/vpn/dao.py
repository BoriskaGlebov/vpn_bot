from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import logger, settings_bot
from bot.dao.base import BaseDAO
from bot.subscription.models import DEVICE_LIMITS
from bot.users.dao import UserDAO
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
        logger.debug(f"[DAO] Проверка лимита VPN конфигов для пользователя {user_id}")
        try:
            user = await UserDAO.find_one_or_none_by_id(
                session=session, data_id=user_id
            )
            if not user:
                logger.warning(
                    f"[DAO] Пользователь {user_id} не найден при проверке лимита конфигов",
                )
                return False
            async with cls.transaction(session=session):
                count = (
                    await session.scalar(
                        select(func.count()).where(VPNConfig.user_id == user_id)
                    )
                    or 0
                )
                logger.debug(f"[DAO] У пользователя {user_id} конфигов: {count}")

                if user and count == 0:
                    return True
                sub_type = user.current_subscription.type
                max_configs = DEVICE_LIMITS.get(sub_type, 0)
                logger.debug(
                    f"[DAO] Лимит конфигов для пользователя {user_id} ({sub_type}): {count}/{max_configs}",
                )
                return count < max_configs
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при припроверке лимита конфиг файлов: {e}")
            raise e

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
        logger.info(
            f"[DAO] Попытка создать новый VPN конфиг для пользователя {user_id}: файл='{file_name}'",
        )
        try:
            if not await cls.can_add_config(session=session, user_id=user_id):
                logger.error(
                    f"[DAO] Создание конфига отклонено — пользователь {user_id} достиг лимита",
                )
                raise ValueError(
                    f"Пользователь {user_id} достиг лимита {settings_bot.max_configs_per_user} конфигов"
                )
            async with cls.transaction(session=session):
                config = VPNConfig(
                    user_id=user_id, file_name=file_name, pub_key=pub_key
                )
                session.add(config)
                logger.success(
                    f"[DAO] Создан новый VPNConfig id={config.id} для пользователя {user_id} (файл='{file_name}')",
                )
                return config
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при добавлении конфиг файла: {e}")
            raise e
