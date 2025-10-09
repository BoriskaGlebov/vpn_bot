from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import logger
from bot.dao.base import BaseDAO
from bot.users.models import Role, User, UserRole
from bot.users.schemas import SRole, SUser


class UserDAO(BaseDAO[User]):
    """Класс для работы с данными пользователей в базе данных.

    Наследует методы от BaseDAO и предоставляет дополнительные
    операции для работы с пользователями.

    Attributes
        model (User): Модель, с которой работает этот DAO.

    """

    model = User  # Модель для работы с данными пользователя

    @classmethod
    async def add_role(cls, session: AsyncSession, role: SRole, user: SUser) -> User:
        """Добавляет роль пользователю.

        Args:
            session (AsyncSession): Асинхронная сессия базы данных.
            role (SRole): Схема роли для добавления.
            user (SUser): Схема пользователя, которому добавляется роль.

        Returns
            User: Обновленный пользователь с добавленной ролью.

        """
        role_query = select(Role).where(Role.name == role.name)
        role_obj = await session.scalar(role_query)
        if not role_obj:
            raise ValueError(f"Роль с именем {role.name} не найдена в базе данных.")
        model_query = select(cls.model).where(cls.model.telegram_id == user.telegram_id)
        user_obj = await session.scalar(model_query)
        if not user_obj:
            raise ValueError(f"Пользователь с {user.telegram_id} -  не найден в БД")
        logger.info(f"Добавление роли {role} пользователю {user}")
        if role_obj not in user_obj.roles:
            # print(user_obj.roles)
            user_obj.roles.append(role_obj)
        try:
            await session.commit()
            logger.info(f"Запись {cls.model.__name__} успешно добавлена")
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении записи: {e}")
            raise e
        return user_obj


class RoleDAO(BaseDAO[Role]):
    """Класс DAO для работы с ролями пользователей.

    Наследует общие методы из `BaseDAO` и обеспечивает доступ к данным
    таблицы `roles`.

    Attributes
        model (type[Role]): Модель ORM, с которой работает данный DAO.

    """

    model = Role


class UserRoleDAO(BaseDAO[UserRole]):
    """Класс DAO для работы со связью между пользователями и ролями.

    Обеспечивает операции с таблицей `user_roles`, которая реализует
    связь "многие ко многим" между `User` и `Role`.

    Attributes
        model (type[UserRole]): Модель ORM, с которой работает данный DAO.

    """

    model = UserRole
