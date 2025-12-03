from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.users.dao import RoleDAO
from bot.users.models import Role, User
from bot.users.schemas import SRole

DEFAULT_ROLES = [
    {"name": "admin", "description": "Администратор"},
    {"name": "founder", "description": "Пользователи с правами основателя"},
    {"name": "user", "description": "Обычный пользователь"},
]


@connection()
async def init_default_roles_admins(session: AsyncSession) -> None:
    """Создаёт базовые роли, если их нет в БД и обновляет список админов."""
    existing_roles = await RoleDAO.find_all(session=session)
    existing_name = {role.name for role in existing_roles}
    for role in DEFAULT_ROLES:
        if role["name"] not in existing_name:
            schema = SRole(**role)
            await RoleDAO.add(session, schema)
    async with session.begin():
        query = select(User.telegram_id).join(User.role).where(Role.name == "admin")
        result = await session.execute(query)
        admins = result.scalars().all()
        settings_bot.admin_ids.update(admins)  # type: ignore[union-attr]
