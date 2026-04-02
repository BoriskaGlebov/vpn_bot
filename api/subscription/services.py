from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    AppError,
    TrialAlreadyUsedError,
    UserNotFoundError,
)
from api.core.mapper.user_mapper import UserMapper
from api.subscription.dao import SubscriptionDAO
from api.subscription.models import SubscriptionType
from api.users.dao import UserDAO
from api.users.schemas import SUserOut, SUserTelegramID
from shared.enums.admin_enum import FilterTypeEnum, RoleEnum
from shared.enums.subscription_enum import ToggleSubscriptionMode


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    @staticmethod
    async def check_premium(
        session: AsyncSession, tg_id: int
    ) -> tuple[bool, RoleEnum, bool, bool]:
        """Проверяет наличие активной премиум-подписки у пользователя.

        Args:
            session: Асинхронная SQLAlchemy сессия.
            tg_id: Telegram ID пользователя.

        Returns
            tuple[bool, RoleEnum, bool]:
                - bool: True, если активна премиум-подписка
                - RoleEnum: роль пользователя
                - bool: активна ли текущая подписка
                - bool: использовал ли триал.

        Raises
            UserNotFoundError: если пользователь не найден
            AppError: если отсутствует current_subscription

        """
        logger.debug("Проверка premium подписки начата: tg_id={}", tg_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=tg_id)
        )
        if not user_model:
            logger.warning("Пользователь не найден: tg_id={}", tg_id)
            raise UserNotFoundError(tg_id=tg_id)
        if user_model.current_subscription is None:
            logger.error("Отсутствует current_subscription: tg_id={}", tg_id)
            raise AppError(message="Некорректно распаковал подписку!")
        premium = user_model.current_subscription.type
        founder = user_model.role
        is_active_sbscr = bool(user_model.current_subscription.is_active)
        logger.info(
            "Проверка premium завершена: tg_id={}, premium={}, active={}",
            tg_id,
            user_model.current_subscription.type,
            user_model.current_subscription.is_active,
        )
        if premium and premium == ToggleSubscriptionMode.PREMIUM:
            return (
                True,
                RoleEnum(founder.name),
                is_active_sbscr,
                user_model.has_used_trial,
            )
        else:
            return (
                False,
                RoleEnum(founder.name),
                is_active_sbscr,
                user_model.has_used_trial,
            )

    @staticmethod
    async def start_trial_subscription(
        session: AsyncSession, tg_id: int, days: int
    ) -> None:
        """Активирует или продлевает trial-подписку пользователя.

        Логика:
            - Если есть активная подписка и trial не использован → продление
            - Если trial уже использован → ошибка
            - Если активной подписки нет → создаётся trial

        Args:
            session: Асинхронная SQLAlchemy сессия.
            tg_id: Telegram ID пользователя.
            days: длительность trial в днях.

        Raises
            UserNotFoundError: если пользователь не найден
            ActiveSubscriptionExistsError: если активна подписка и trial уже использован
            TrialAlreadyUsedError: если trial уже использован

        """
        logger.debug("Старт обработки trial подписки: tg_id={}, days={}", tg_id, days)
        schema_user = SUserTelegramID(telegram_id=tg_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user
        )
        try:
            if (
                user_model
                and user_model.current_subscription
                and user_model.current_subscription.is_active
                and not user_model.has_used_trial
            ):
                logger.debug("Обнаружена активная подписка: tg_id={}", tg_id)
                user_model.current_subscription.extend(days=days)
                user_model.has_used_trial = True
                logger.info(
                    "Trial подписка продлена за счет активной: tg_id={}, days={}",
                    tg_id,
                    days,
                )
                return
            if (
                user_model
                and user_model.current_subscription
                and user_model.current_subscription.is_active
            ):
                logger.warning(
                    "Невозможно активировать trial — уже есть активная подписка: tg_id={}",
                    tg_id,
                )
                raise ActiveSubscriptionExistsError()
            if user_model and user_model.has_used_trial:
                logger.warning("Trial уже был использован: tg_id={}", tg_id)
                raise TrialAlreadyUsedError()

            await SubscriptionDAO.activate_subscription(
                session=session,
                stelegram_id=schema_user,
                days=days,
                sub_type=SubscriptionType.TRIAL,
            )
            await session.refresh(
                user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
            )
            logger.debug("Обновление данных подписки завершено: tg_id={}", tg_id)
        except (TrialAlreadyUsedError, AppError):
            raise

    @staticmethod
    async def activate_paid_subscription(
        session: AsyncSession, user_id: int, months: int, premium: bool
    ) -> SUserOut:
        """Активирует или продлевает платную подписку пользователя.

        Поведение:
            - Если активная подписка нужного типа существует → продление
            - Если пользователь FOUNDER → всегда форсируется PREMIUM
            - Иначе создаётся новая подписка

        Args:
            session: Асинхронная SQLAlchemy сессия.
            user_id: Telegram ID пользователя.
            months: срок подписки в месяцах.
            premium: True → PREMIUM, False → STANDARD

        Returns
            SUserOut: обновлённый пользователь

        Raises
            UserNotFoundError: если пользователь не найден

        """
        logger.debug(
            "Начало активации платной подписки: user_id={}, months={}, premium={}",
            user_id,
            months,
            premium,
        )
        schema_user = SUserTelegramID(telegram_id=user_id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user
        )
        if not user_model:
            logger.warning("Пользователь не найден: user_id={}", user_id)
            raise UserNotFoundError(tg_id=user_id)
        sub_type = SubscriptionType.PREMIUM if premium else SubscriptionType.STANDARD
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
                "Продление подписки: user_id={}, months={}, type={}",
                user_id,
                months,
                sub_type,
            )
            active_sub.extend(months=months)
            return await UserMapper.to_schema(user=user_model)
        elif user_model.role.name == FilterTypeEnum.FOUNDER:
            logger.info(
                "Основатель: принудительная установка PREMIUM подписки: user_id={}, months={}",
                user_id,
                months,
            )
            current_sub = user_model.current_subscription
            if current_sub is not None:
                current_sub.extend(months=months)
                current_sub.type = SubscriptionType.PREMIUM
                return await UserMapper.to_schema(user=user_model)
        logger.info(
            "Создание новой подписки: user_id={}, months={}, type={}",
            user_id,
            months,
            sub_type,
        )
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months, sub_type=sub_type
        )
        logger.success(
            "Подписка успешно активирована: user_id={}, months={}",
            user_id,
            months,
        )
        await session.refresh(
            user_model, attribute_names=["subscriptions", "role", "vpn_configs"]
        )
        return await UserMapper.to_schema(user=user_model)
