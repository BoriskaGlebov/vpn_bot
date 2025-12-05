from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.enums import AdminModeKeys
from bot.app_error.base_error import UserNotFoundError
from bot.users.dao import RoleDAO, UserDAO
from bot.users.router import m_admin
from bot.users.schemas import SRole, SUserOut, SUserTelegramID


class AdminService:
    """Сервис для бизнес-логики управления пользователями и их ролями."""

    @staticmethod
    async def get_user_by_telegram_id(
        session: AsyncSession, telegram_id: int
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
        user_schema = SUserOut.model_validate(user)
        return user_schema

    @staticmethod
    async def get_users_by_filter(
        session: AsyncSession, filter_type: str
    ) -> list[SUserOut]:
        """Получает список пользователей по фильтру роли.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            filter_type (str): Имя роли или 'all' для всех пользователей.

        Returns
            List[SUserOut]: Список пользователей схемы.

        """
        users = await UserDAO.get_users_by_roles(
            session=session, filter_type=filter_type
        )
        return [SUserOut.model_validate(user) for user in users]

    @staticmethod
    async def format_user_text(suser: SUserOut, key: str = AdminModeKeys.USER) -> str:
        """Форматирует текст пользователя для сообщений.

        Args:
            suser (SUserOut): Схема пользователя.
            key (str): Ключ шаблона текста в `m_admin`.

        Returns
            str: Отформатированный текст пользователя.

        """
        template: str = m_admin[key]
        return template.format(
            first_name=suser.first_name or "-",
            last_name=suser.last_name or "-",
            username=suser.username or "-",
            telegram_id=suser.telegram_id or "-",
            roles=str(suser.role),
            subscription=str(suser.subscription) or "-",
        )

    @staticmethod
    async def change_user_role(
        session: AsyncSession, telegram_id: int, role_name: str
    ) -> SUserOut:
        """Меняет роль пользователя и при необходимости активирует подписку.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            telegram_id (int): ID пользователя в Telegram.
            role_name (str): Имя новой роли.

        Returns
            SUserOut: Схема пользователь.

        Raises
            UserNotFoundError: Если пользователь или роль не найдены.

        """
        user = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=telegram_id)
        )
        role = await RoleDAO.find_one_or_none(session, filters=SRole(name=role_name))

        if not user or not role:
            raise UserNotFoundError(tg_id=telegram_id)
        changed_user = await UserDAO.change_role(session=session, user=user, role=role)
        return SUserOut.model_validate(changed_user)

    @staticmethod
    async def extend_user_subscription(
        session: AsyncSession, telegram_id: int, months: int
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
        return SUserOut.model_validate(changed_user)
