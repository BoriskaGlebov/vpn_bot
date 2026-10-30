from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.app_error.base_error import UserNotFoundError
from api.core.config import settings_api
from api.core.mapper.user_mapper import UserMapper
from api.referrals.models import Referral
from api.subscription.models import SubscriptionType
from api.users.dao import UserDAO
from api.users.models import User
from api.users.schemas import (
    SRole,
    SUser,
    SUsernameUpdate,
    SUserOut,
    SUserTelegramID,
    SUserWithReferralStats,
)


class UserService:
    """Сервис для управления пользователями."""

    async def register_or_get_user(
        self, session: AsyncSession, telegram_user: SUser
    ) -> tuple[SUserOut, bool]:
        """Регистрирует пользователя, если он отсутствует, или возвращает существующего.

        Если пользователь с данным Telegram ID отсутствует в базе данных, создаётся новая
        запись, а также автоматически назначается роль:
        - "admin" — если Telegram ID находится в списке `settings_bot.ADMIN_IDS`
        - "user" — для всех остальных пользователей

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy для работы с БД.
            telegram_user (SUser): Схема с данными из телеграм пользователя.

        Returns
            tuple[SUserOut, bool]: Кортеж из:
                - экземпляра схемы `SUserOut`
                - булевого флага:
                    - `True`, если пользователь был создан;
                    - `False`, если пользователь уже существовал.

        """
        logger.debug("Начало обработки пользователя")
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=telegram_user.telegram_id),
            options=UserDAO.base_options,
        )
        if user:
            logger.info("Пользователь найден в базе")
            if telegram_user.username and telegram_user.username != user.username:
                # username изменяем и переиспользуем — обновляем при
                # каждом входе, чтобы хранимое значение не старело. Пустой
                # username во входящих данных НЕ считается сменой: часть
                # вызовов этого эндпоинта (bot/vpn/services.py,
                # bot/core/filters.py — получить/создать пользователя по
                # одному telegram_id, не полный профиль) всегда шлют
                # username=None, иначе каждый такой вызов затирал бы
                # сохранённый username пустым значением.
                logger.info(
                    "Username изменился telegram_id={}: {!r} -> {!r}",
                    telegram_user.telegram_id,
                    user.username,
                    telegram_user.username,
                )
                await UserDAO.update(
                    session=session,
                    filters=SUserTelegramID(telegram_id=telegram_user.telegram_id),
                    values=SUsernameUpdate(username=telegram_user.username),
                )
                await session.refresh(user)
            return UserMapper.to_schema(user), False
        logger.info("Пользователь не найден, создаём нового")
        is_admin = telegram_user.telegram_id in settings_api.core.admin_ids
        schema_user = SUser(
            telegram_id=telegram_user.telegram_id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )
        schema_role = SRole(name="admin" if is_admin else "user")
        logger.debug(f"Назначается роль: {schema_role}")
        # «Администратор получает бессрочный премиум» — продуктовое правило,
        # решается здесь, в сервисе, а не в UserDAO (#244): DAO только
        # сохраняет то, что ему передали.
        try:
            async with session.begin_nested():
                user = await UserDAO.add_role_subscription(
                    session=session,
                    values_user=schema_user,
                    values_role=schema_role,
                    subscription_is_active=is_admin,
                    subscription_type=SubscriptionType.PREMIUM if is_admin else None,
                )
        except IntegrityError:
            # Гонка: между нашим SELECT и INSERT другой запрос успел создать
            # пользователя с тем же telegram_id (двойной тап /start, повторная
            # доставка Telegram-апдейта). SAVEPOINT откатил только эту вставку,
            # внешняя транзакция (get_session) остаётся рабочей — можно читать.
            logger.info(
                "Гонка при регистрации telegram_id={}: запись уже создана "
                "другим запросом, возвращаем существующего пользователя",
                telegram_user.telegram_id,
            )
            user = await UserDAO.find_one_or_none(
                session=session,
                filters=SUserTelegramID(telegram_id=telegram_user.telegram_id),
                options=UserDAO.base_options,
            )
            if user is None:
                raise
            return UserMapper.to_schema(user), False
        logger.success("Пользователь успешно создан")
        return UserMapper.to_schema(user), True

    async def get_user_with_referrals(
        self,
        session: AsyncSession,
        telegram_id: int,
    ) -> SUserWithReferralStats:
        """Получает пользователя с реферальной статистикой."""
        logger.debug("Получение пользователя с реферальной статистикой")

        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=telegram_id),
            options=[
                *UserDAO.base_options,
                selectinload(User.invited_users)
                .selectinload(Referral.invited)
                .selectinload(User.subscriptions),
            ],
        )
        if not user:
            logger.warning(f"Пользователь с telegram_id={telegram_id} не найден")
            raise UserNotFoundError(tg_id=telegram_id)

        logger.info(f"Пользователь найден: {user.id}, считаем рефералов")
        return UserMapper.to_schema_with_referrals(user)
