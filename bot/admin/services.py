import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.users.dao import RoleDAO, UserDAO
from bot.users.models import Role, User
from bot.users.router import m_admin
from bot.users.schemas import SRole, SUserTelegramID


class AdminService:
    """Сервис для бизнес-логики управления пользователями и их ролями."""

    async def get_user_by_telegram_id(
        self, session: AsyncSession, telegram_id: int
    ) -> User:
        """Возвращает пользователя по Telegram ID.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.

        Returns
            User: Объект пользователя.

        Raises
            ValueError: Если пользователь не найден.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        if not user:
            raise ValueError(f"Пользователь с telegram_id={telegram_id} не найден")
        return user

    @staticmethod
    async def get_users_by_filter(
        session: AsyncSession, filter_type: str
    ) -> list[User]:
        """Получает список пользователей по фильтру роли.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            filter_type (str): Имя роли или 'all' для всех пользователей.

        Returns
            List[User]: Список пользователей.

        """
        stmt = select(User).join(User.role).options(selectinload(User.role))
        if filter_type != "all":
            stmt = stmt.where(Role.name == filter_type)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def format_user_text(user: User, key: str = "user") -> str:
        """Форматирует текст пользователя для сообщений.

        Args:
            user (User): Объект пользователя.
            key (str): Ключ шаблона текста в `m_admin`.

        Returns
            str: Отформатированный текст пользователя.

        """
        template: str = m_admin[key]
        return template.format(
            first_name=user.first_name or "-",
            last_name=user.last_name or "-",
            username=user.username or "-",
            telegram_id=user.telegram_id or "-",
            roles=user.role,
            subscription=user.subscription or "-",
        )

    async def change_user_role(
        self, session: AsyncSession, telegram_id: int, role_name: str
    ) -> User:
        """Меняет роль пользователя и при необходимости активирует подписку.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.
            role_name (str): Имя новой роли.

        Returns
            User: Обновлённый пользователь.

        Raises
            ValueError: Если пользователь или роль не найдены.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        role = await RoleDAO.find_one_or_none(session, filters=SRole(name=role_name))

        if not user or not role:
            raise ValueError(
                f"Пользователь или роль не найдены ({telegram_id}/{role_name})"
            )

        user.role = role

        if role.name == "founder":
            now = datetime.datetime.now(tz=datetime.UTC)
            next_year = datetime.datetime(now.year + 1, 1, 1, tzinfo=datetime.UTC)
            delta = next_year - now
            user.subscription.activate(days=delta.days)

        await session.flush([user, user.subscription])
        await session.commit()
        return user

    async def extend_user_subscription(
        self, session: AsyncSession, telegram_id: int, months: int
    ) -> User:
        """Продлевает активную подписку пользователя.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.
            months (int): Количество месяцев продления.

        Returns
            User: Обновлённый пользователь.

        Raises
            ValueError: Если пользователь не найден или подписка не активна.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        if not user:
            raise ValueError(f"Пользователь {telegram_id} не найден")

        subscription = user.subscription
        if subscription.is_active:
            subscription.extend(months=months)
        else:
            raise ValueError("Подписка не активна — продление невозможно")

        await session.flush([user])
        await session.commit()
        return user
