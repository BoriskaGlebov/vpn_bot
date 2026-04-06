from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import UserNotFoundError
from api.subscription.models import DEVICE_LIMITS
from api.users.dao import UserDAO
from api.users.schemas import SUserTelegramID
from api.vpn.dao import VPNConfigDAO
from api.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateResponse,
)


class VPNService:
    """Сервис для работы с VPN-конфигами и подписками пользователей.

    Отвечает за проверку лимита, добавление конфигов и получение информации
    о подписке и VPN-конфигурациях пользователя.
    """

    async def check_limit(
        self,
        session: AsyncSession,
        tg_id: int,
    ) -> SVPNCheckLimitResponse:
        """Проверяет, может ли пользователь создать новый VPN конфиг.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.

        Raises
            UserNotFoundError: Если пользователь не найден или у него нет подписки.

        Returns
            SVPNCheckLimitResponse: Информация о лимите конфигов и текущем количестве.

        """
        logger.debug("Проверка лимитов tg_id={}", tg_id)
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
            options=UserDAO.base_options,
        )
        if not user or not user.current_subscription:
            logger.warning("Пользователь или подписка не найдены tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)

        can_add = await VPNConfigDAO.can_add_config(
            session=session,
            user_id=user.id,
        )

        limit = DEVICE_LIMITS.get(user.current_subscription.type, 0)
        current = len(user.vpn_configs)
        logger.info(
            "Проверка лимита VPN tg_id={} can_add={} current={} limit={}",
            tg_id,
            can_add,
            current,
            limit,
        )
        return SVPNCheckLimitResponse(
            can_add=can_add,
            limit=limit,
            current=current,
        )

    async def add_config(
        self,
        session: AsyncSession,
        tg_id: int,
        file_name: str,
        pub_key: str,
    ) -> SVPNCreateResponse:
        """Создаёт и сохраняет новый VPN конфиг для пользователя.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.
            file_name (str): Название файла конфигурации.
            pub_key (str): Публичный ключ пользователя.

        Raises
            UserNotFoundError: Если пользователь не найден.

        Returns
            SVPNCreateResponse: Подтверждение создания конфига с именем файла и публичным ключом.

        """
        logger.debug("Добавление конфига tg_id={} file_name={}", tg_id, file_name)

        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
            options=UserDAO.base_options,
        )
        if not user:
            logger.warning("Пользователь не найден tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)

        await VPNConfigDAO.add_config(
            session=session,
            user_id=user.id,
            file_name=file_name,
            pub_key=pub_key,
        )
        logger.info("Создан VPN конфиг tg_id={} file_name={}", tg_id, file_name)

        return SVPNCreateResponse(
            file_name=file_name,
            pub_key=pub_key,
        )
