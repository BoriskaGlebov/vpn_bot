from sqlalchemy.ext.asyncio import AsyncSession

from bot.dao.base import BaseDAO
from bot.users.models import Role, User
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
    async def add_role_subscription(
        cls,
        session: AsyncSession,
        values_user: SUser,
        values_role: SRole,
    ) -> User:
        pass


class RoleDAO(BaseDAO[Role]):
    """Класс DAO для работы с ролями пользователей.

    Наследует общие методы из `BaseDAO` и обеспечивает доступ к данным
    таблицы `roles`.

    Attributes
        model (type[Role]): Модель ORM, с которой работает данный DAO.

    """

    model = Role
