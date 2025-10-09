from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import connection
from bot.users.dao import RoleDAO
from bot.users.schemas import SRole

DEFAULT_ROLES = [
    {"name": "admin", "description": "Администратор"},
    {"name": "founder", "description": "Пользователи с правами основателя"},
    {"name": "user", "description": "Обычный пользователь"},
]


@connection()
async def init_default_roles(session: AsyncSession) -> None:
    """Создаёт базовые роли, если их нет в БД."""
    existing_roles = await RoleDAO.find_all(session=session)
    existing_name = {role.name for role in existing_roles}
    for role in DEFAULT_ROLES:
        if role["name"] not in existing_name:
            schema = SRole(**role)
            await RoleDAO.add(session, schema)


# if __name__ == "__main__":
#     import asyncio
#
#     asyncio.run(init_default_roles())
