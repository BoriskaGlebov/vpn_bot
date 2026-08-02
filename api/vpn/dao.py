from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    AppError,
    SubscriptionNotFoundError,
    VPNLimitError,
)
from api.core.config import settings_api
from api.core.dao.base import BaseDAO
from api.subscription.models import DEVICE_LIMITS
from api.users.dao import UserDAO
from api.vpn.models import VPNConfig


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
                session=session,
                data_id=user_id,
            )
            if not user:
                logger.warning(
                    f"[DAO] Пользователь {user_id} не найден при проверке лимита конфигов",
                )
                return False
            count = (
                await session.scalar(
                    select(func.count()).where(VPNConfig.user_id == user_id)
                )
                or 0
            )
            logger.debug(f"[DAO] У пользователя {user_id} конфигов: {count}")
            if not user.current_subscription or not user.current_subscription.is_active:
                logger.warning("Нет активной подписки: user_id={}", user_id)
                raise SubscriptionNotFoundError(user_id=user_id, username=user.username)
            if user and count == 0:
                return True
            sub_type = user.current_subscription.type
            max_configs = DEVICE_LIMITS.get(sub_type, 0)
            logger.debug(
                f"[DAO] Лимит конфигов для пользователя {user_id} ({sub_type}): {count}/{max_configs}",
            )
            return count < max_configs

        except SQLAlchemyError:
            logger.exception("[DAO] Ошибка при проверке лимита конфиг файлов")
            raise

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
                # Ожидаемое бизнес-ограничение (превышен лимит устройств),
                # а не системная ошибка.
                logger.warning(
                    f"[DAO] Создание конфига отклонено — пользователь {user_id} достиг лимита",
                )
                user = await UserDAO.find_one_or_none_by_id(
                    session=session, data_id=user_id
                )
                if user is None:
                    raise AppError(
                        message=f"Не удалось найти пользователя по внутреннему ID={user_id}"
                    )
                raise VPNLimitError(
                    user_id=user_id,
                    limit=settings_api.core.max_configs_per_user,
                    username=user.username if user else "unknown_username",
                )

            config = VPNConfig(user_id=user_id, file_name=file_name, pub_key=pub_key)
            session.add(config)
            logger.success(
                f"[DAO] Создан новый VPNConfig id={config.id} для пользователя {user_id} (файл='{file_name}')",
            )
            return config
        except SQLAlchemyError:
            logger.exception("[DAO] Ошибка при добавлении конфиг файла")
            raise
