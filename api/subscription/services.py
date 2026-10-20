from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    SubscriptionNotFoundError,
    TrialAlreadyUsedError,
    UserNotFoundError,
)
from api.core.mapper.user_mapper import UserMapper
from api.subscription.dao import SubscriptionDAO
from api.subscription.models import SubscriptionType
from api.subscription.schemas import SSubscriptionCheck, SSubscriptionInfo, SVPNConfig
from api.users.dao import UserDAO
from api.users.schemas import SUserOut, SUserTelegramID
from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import (
    SubscriptionInfoStatus,
    ToggleSubscriptionMode,
    TrialStatus,
)


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    @staticmethod
    async def check_premium(session: AsyncSession, tg_id: int) -> SSubscriptionCheck:
        """Проверяет наличие активной премиум-подписки у пользователя.

        Args:
            session: Асинхронная SQLAlchemy сессия.
            tg_id: Telegram ID пользователя.

        Returns
            SSubscriptionCheck: активна ли премиум-подписка, роль
                пользователя, активность текущей подписки, использован ли
                триал.

        Raises
            UserNotFoundError: если пользователь не найден
            SubscriptionNotFoundError: если отсутствует current_subscription

        """
        logger.debug("Проверка premium подписки начата: tg_id={}", tg_id)
        user_model = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
            options=UserDAO.base_options,
        )
        if not user_model:
            logger.warning("Пользователь не найден: tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)
        subscription = user_model.current_subscription
        if subscription is None:
            # Ожидаемая ситуация (у пользователя ещё нет подписки), а не
            # системная ошибка — уровень как у соседнего "не найден" выше.
            logger.warning("Отсутствует current_subscription: tg_id={}", tg_id)
            raise SubscriptionNotFoundError(
                user_id=user_model.id, username=user_model.username
            )

        premium = subscription.type
        is_active_sbscr = bool(subscription.is_active)
        logger.info(
            "Проверка premium завершена: tg_id={}, premium={}, active={}",
            tg_id,
            subscription.type,
            subscription.is_active,
        )
        return SSubscriptionCheck(
            premium=bool(premium and premium == ToggleSubscriptionMode.PREMIUM),
            role=RoleEnum(user_model.role.name),
            is_active=is_active_sbscr,
            used_trial=user_model.has_used_trial,
        )

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, tg_id: int, days: int
    ) -> TrialStatus:
        """Активирует или продлевает trial-подписку пользователя.

        Логика:
            - Если есть активная подписка и trial не использован → продление
            - Если trial уже использован → ошибка
            - Если активной подписки нет → создаётся trial

        Args:
            session: Асинхронная SQLAlchemy сессия.
            tg_id: Telegram ID пользователя.
            days: длительность trial в днях.

        Returns
            TrialStatus: EXTENDED, если продлена существующая активная
                подписка, STARTED, если создана новая trial-подписка.

        Raises
            UserNotFoundError: если пользователь не найден
            TrialAlreadyUsedError: если trial уже использован

        """
        logger.debug("Старт обработки trial подписки: tg_id={}, days={}", tg_id, days)
        schema_user = SUserTelegramID(telegram_id=tg_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user, options=UserDAO.base_options
        )
        if not user_model:
            logger.warning("Пользователь не найден: tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)
        subscription = user_model.current_subscription

        if subscription and subscription.is_active and not user_model.has_used_trial:
            logger.debug("Продление trial через активную подписку: tg_id={}", tg_id)

            subscription.extend(days=days)
            user_model.has_used_trial = True

            logger.info(
                "Trial продлён через активную подписку: tg_id={}, days={}",
                tg_id,
                days,
            )
            return TrialStatus.EXTENDED

        # Вторая ветвь (subscription активна и has_used_trial) была
        # недостижима — подмножество проверки ниже с тем же исключением и
        # аргументами, поэтому убрана.
        if user_model.has_used_trial:
            logger.warning("Trial уже использован: tg_id={}", tg_id)
            raise TrialAlreadyUsedError(
                user_id=user_model.id, username=user_model.username
            )

        # Правило «один раз» целиком в сервисе — Subscription.activate()
        # больше не проверяет и не выставляет has_used_trial сам.
        user_model.has_used_trial = True
        await SubscriptionDAO.activate_subscription(
            session=session,
            stelegram_id=schema_user,
            days=days,
            sub_type=SubscriptionType.TRIAL,
        )
        await session.refresh(
            user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
        )
        logger.debug("Trial подписка активирована: tg_id={}", tg_id)
        return TrialStatus.STARTED

    @staticmethod
    async def activate_paid_subscription(
        session: AsyncSession, tg_id: int, months: int, premium: bool
    ) -> SUserOut:
        """Активирует или продлевает платную подписку пользователя.

        Поведение:
            - Если активная подписка нужного типа существует → продление
            - Если пользователь FOUNDER → всегда форсируется тип подписки FOUNDER
              (аргумент `premium` для него игнорируется)
            - Иначе создаётся новая подписка (PREMIUM или STANDARD по `premium`)

        Args:
            session: Асинхронная SQLAlchemy сессия.
            tg_id: Telegram ID пользователя.
            months: срок подписки в месяцах.
            premium: True → PREMIUM, False → STANDARD

        Returns
            SUserOut: обновлённый пользователь

        Raises
            UserNotFoundError: если пользователь не найден

        """
        logger.debug(
            "Начало активации платной подписки: tg_id={}, months={}, premium={}",
            tg_id,
            months,
            premium,
        )
        schema_user = SUserTelegramID(telegram_id=tg_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user, options=UserDAO.base_options
        )
        if not user_model:
            logger.warning("Пользователь не найден: tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)
        if user_model.role.name == RoleEnum.FOUNDER:
            sub_type = SubscriptionType.FOUNDER
        elif premium:
            sub_type = SubscriptionType.PREMIUM
        else:
            sub_type = SubscriptionType.STANDARD
        active_sub = next(
            (
                sbscr
                for sbscr in user_model.subscriptions
                if sbscr.is_active and sub_type == sbscr.type
            ),
            None,
        )
        if active_sub:
            logger.info(
                "Продление подписки: tg_id={}, months={}, type={}",
                tg_id,
                months,
                sub_type,
            )
            active_sub.extend(months=months)
            return UserMapper.to_schema(user=user_model)
        elif user_model.role.name == RoleEnum.FOUNDER:
            logger.info(
                "Основатель: принудительная установка подписки FOUNDER: tg_id={}, months={}",
                tg_id,
                months,
            )
            current_sub = user_model.current_subscription
            if current_sub is not None:
                current_sub.extend(months=months)
                current_sub.type = SubscriptionType.FOUNDER
                return UserMapper.to_schema(user=user_model)
        # Активная подписка найдена выше только среди подписок того же
        # типа (sub_type == sbscr.type) — активная подписка ДРУГОГО типа
        # (например, старый TRIAL) сюда не попадает и без этой деактивации
        # осталась бы брошенной: is_active=True после создания новой записи.
        for existing_sub in user_model.subscriptions:
            if existing_sub.is_active:
                logger.info(
                    "Деактивация прежней подписки другого типа: tg_id={}, "
                    "type={}, new_type={}",
                    tg_id,
                    existing_sub.type,
                    sub_type,
                )
                existing_sub.deactivate()
        logger.info(
            "Создание новой подписки: tg_id={}, months={}, type={}",
            tg_id,
            months,
            sub_type,
        )
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months, sub_type=sub_type
        )
        logger.success(
            "Подписка успешно активирована: tg_id={}, months={}",
            tg_id,
            months,
        )
        await session.refresh(
            user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
        )
        return UserMapper.to_schema(user=user_model)

    async def get_subscription_info(
        self,
        session: AsyncSession,
        tg_id: int,
    ) -> SSubscriptionInfo:
        """Возвращает информацию о подписке пользователя и его VPN-конфигах.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            tg_id (int): Telegram ID пользователя.

        Raises
            UserNotFoundError: Если пользователь не найден.

        Returns
            SSubscriptionInfo: Статус подписки, тип, оставшиеся дни, дата окончания и список конфигов.

        """
        logger.debug("Получение информации по подписке tg_id={}", tg_id)
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=tg_id),
            options=UserDAO.base_options,
        )
        if not user:
            logger.warning("Пользователь не найден tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)

        subscription = user.current_subscription
        if not subscription:
            logger.info("У пользователя нет подписки tg_id={}", tg_id)
            return SSubscriptionInfo(
                status=SubscriptionInfoStatus.NO_SUBSCRIPTION,
                subscription_type=None,
                remaining=None,
                configs=[],
                end_date=None,
            )

        status = (
            SubscriptionInfoStatus.ACTIVE
            if subscription.is_active
            else SubscriptionInfoStatus.INACTIVE
        )

        # Текст для показа пользователю ("N дней" / "UNLIMITED") собирает бот —
        # отсюда уходит только число (или None для бессрочной подписки).
        remaining = subscription.remaining_days()
        logger.info(
            "Инфо подписки VPN tg_id={} status={} type={}",
            tg_id,
            status,
            subscription.type.value if subscription.type else None,
        )
        return SSubscriptionInfo(
            status=status,
            subscription_type=subscription.type.value if subscription.type else None,
            remaining=remaining,
            end_date=subscription.end_date if subscription.end_date else None,
            configs=[
                SVPNConfig(
                    id=c.id,
                    file_name=c.file_name,
                    node_name=c.node_name,
                    created_at=c.created_at,
                )
                for c in user.vpn_configs
            ],
        )
