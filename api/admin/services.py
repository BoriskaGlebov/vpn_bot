from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.enums import FilterTypeEnum, RoleEnum
from api.app_error.base_error import RoleNotFoundError, UserNotFoundError
from api.core.mapper.user_mapper import UserMapper
from api.users.dao import RoleDAO, UserDAO
from api.users.schemas import (
    SRole,
    SUserOut,
    SUserTelegramID,
)


class AdminService:
    """Сервис для бизнес-логики управления пользователями и их ролями."""

    @classmethod
    async def get_user_by_telegram_id(
        cls, session: AsyncSession, telegram_id: int
    ) -> SUserOut:
        """Возвращает пользователя по Telegram ID.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.

        Returns
            SUserOut: Схема пользователя.

        Raises
            UserNotFoundError: Если пользователь не найден.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        if not user:
            raise UserNotFoundError(tg_id=telegram_id)
        user_schema = await UserMapper.to_schema(user)
        return user_schema

    @classmethod
    async def get_users_by_filter(
        cls, session: AsyncSession, filter_type: FilterTypeEnum
    ) -> list[SUserOut]:
        """Получает список пользователей по фильтру роли.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            filter_type (UserFilter): Фильтр пользователей:
                - ALL — все пользователи
                - USER — обычные пользователи
                - ADMIN — администраторы
                - FOUNDER — владельцы системы

        Returns
            List[SUserOut]: Список пользователей схемы.

        """
        users = await UserDAO.get_users_by_roles(
            session=session, filter_type=filter_type.value
        )
        return [await UserMapper.to_schema(user) for user in users]

    @classmethod
    async def change_user_role(
        cls, session: AsyncSession, telegram_id: int, role_name: RoleEnum
    ) -> SUserOut:
        """Меняет роль пользователя и при необходимости активирует подписку.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.
            role_name (RoleEnum): Новая роль пользователя.

        Returns
            SUserOut: Схема пользователь.

        Raises
            UserNotFoundError: Если пользователь или роль не найдены.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        role = await RoleDAO.find_one_or_none(
            session, filters=SRole(name=role_name.value)
        )

        if not user:
            raise UserNotFoundError(tg_id=telegram_id)
        if not role:
            raise RoleNotFoundError(role_name=role_name)

        changed_user = await UserDAO.change_role(session=session, user=user, role=role)
        user_schema = await UserMapper.to_schema(changed_user)
        return user_schema

    @classmethod
    async def extend_user_subscription(
        cls, session: AsyncSession, telegram_id: int, months: int
    ) -> SUserOut:
        """Продлевает активную подписку пользователя.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.
            months (int): Количество месяцев продления.

        Returns
            SUserOut: Схема пользователь.

        Raises
            UserNotFoundError: Если пользователь не найден.
            SubscriptionNotFoundError: Подписка не активна.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        if not user:
            raise UserNotFoundError(tg_id=telegram_id)
        changed_user = await UserDAO.extend_subscription(
            session=session, user=user, months=months
        )
        user_schema = await UserMapper.to_schema(changed_user)
        return user_schema
