from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import UserNotFoundError
from api.subscription.models import DEVICE_LIMITS
from api.users.dao import UserDAO
from api.vpn.dao import VPNConfigDAO
from shared.schemas.users import SUserTelegramID
from shared.schemas.vpn import (
    SVPNCheckLimitResponse,
    SVPNConfig,
    SVPNCreateResponse,
    SVPNSubscriptionInfo,
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
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
        )
        if not user or not user.current_subscription:
            raise UserNotFoundError(tg_id=tg_id)

        can_add = await VPNConfigDAO.can_add_config(
            session=session,
            user_id=user.id,
        )

        limit = DEVICE_LIMITS.get(user.current_subscription.type, 0)
        current = len(user.vpn_configs)

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
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
        )
        if not user:
            raise UserNotFoundError(tg_id=tg_id)

        await VPNConfigDAO.add_config(
            session=session,
            user_id=user.id,
            file_name=file_name,
            pub_key=pub_key,
        )

        return SVPNCreateResponse(
            file_name=file_name,
            pub_key=pub_key,
        )

    async def get_subscription_info(
        self,
        session: AsyncSession,
        tg_id: int,
    ) -> SVPNSubscriptionInfo:
        """Возвращает информацию о подписке пользователя и его VPN-конфигах.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.

        Raises
            UserNotFoundError: Если пользователь не найден.

        Returns
            SVPNSubscriptionInfo: Статус подписки, тип, оставшиеся дни, дата окончания и список конфигов.

        """
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
        )
        if not user:
            raise UserNotFoundError(tg_id=tg_id)

        subscription = user.current_subscription
        if not subscription:
            return SVPNSubscriptionInfo(
                status="no_subscription",
                subscription_type=None,
                remaining="",
                configs=[],
                end_date=None,
            )

        status = "active" if subscription.is_active else "inactive"

        remaining_days = subscription.remaining_days()
        remaining = "UNLIMITED" if remaining_days is None else f"{remaining_days} дней"

        return SVPNSubscriptionInfo(
            status=status,
            subscription_type=subscription.type.value if subscription.type else None,
            remaining=remaining,
            end_date=subscription.end_date if subscription.end_date else None,
            configs=[SVPNConfig(file_name=c.file_name) for c in user.vpn_configs],
        )
