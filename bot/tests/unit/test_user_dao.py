import pytest
from sqlalchemy import select

from bot.users.dao import UserDAO
from bot.users.models import Role, User
from bot.users.schemas import SRole, SUser


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "telegram_id, username, role_name",
    [
        (1, "alice", "admin"),
        (2, "bob", "moderator"),
        (3, "charlie", "viewer"),
        (4, "bred", "viewer"),
        (5, "dave", "moderator"),
        (6, "nigan", "admin"),
    ],
)
async def test_add_role(session, telegram_id, username, role_name):
    # Создаём пользователя и роль
    user = User(telegram_id=telegram_id, username=username)
    session.add(user)

    # Проверяем, существует ли роль
    existing_role = await session.scalar(select(Role).where(Role.name == role_name))
    if not existing_role:
        role = Role(name=role_name)
        session.add(role)
    else:
        role = existing_role

    await session.commit()

    # Формируем схемы
    user_schema = SUser(telegram_id=telegram_id, username=username)
    role_schema = SRole(name=role_name)

    # Добавляем роль пользователю
    updated_user = await UserDAO.add_role(session, role_schema, user_schema)

    # Проверяем, что роль добавилась
    assert updated_user is not None
    assert any(
        r.name == role_name for r in updated_user.roles
    ), f"Роль '{role_name}' не добавилась пользователю {username}"
