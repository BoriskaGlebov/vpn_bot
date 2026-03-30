import pytest
from sqlalchemy import select

from bot.users.dao import UserDAO
from bot.users.models import Role
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
@pytest.mark.users
async def test_add_role_subscription(session, telegram_id, username, role_name):
    existing_role = await session.scalar(select(Role).where(Role.name == role_name))
    if not existing_role:
        role = Role(name=role_name)
        session.add(role)
    else:
        role = existing_role

    await session.commit()

    user_schema = SUser(telegram_id=telegram_id, username=username)
    role_schema = SRole(name=role_name)
    #
    updated_user = await UserDAO.add_role_subscription(
        session=session, values_user=user_schema, values_role=role_schema
    )

    assert updated_user is not None
    assert (
        role.name == updated_user.role.name
    ), f"Роль '{role_name}' не добавилась пользователю {username}"
