import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.services import AdminService
from bot.users.models import User


@pytest.mark.asyncio
@pytest.mark.admin
async def test_get_user_by_telegram_id_integration(session: AsyncSession, setup_users):
    user = setup_users[0]  # Admin
    user_schema = await AdminService.get_user_by_telegram_id(
        session=session,
        telegram_id=user.telegram_id,
    )

    assert user_schema.telegram_id == user.telegram_id
    assert user_schema.username == user.username


@pytest.mark.asyncio
@pytest.mark.admin
async def test_change_user_role_integration(
    session: AsyncSession, setup_users, setup_roles
):
    user = setup_users[2]  # обычный user
    new_role = setup_roles[0]  # admin

    user_schema = await AdminService.change_user_role(
        session=session,
        telegram_id=user.telegram_id,
        role_name=new_role.name,
    )

    # Проверяем роль в базе
    refreshed_user = await session.get(User, user.id)
    assert refreshed_user.role.name == new_role.name
    assert user_schema.role.name == new_role.name


@pytest.mark.asyncio
@pytest.mark.admin
async def test_extend_user_subscription_integration(session: AsyncSession, setup_users):
    user = setup_users[2]  # user с FREE подпиской
    user.subscriptions[0].is_active = True
    await session.commit()

    months = 3
    user_schema = await AdminService.extend_user_subscription(
        session=session,
        telegram_id=user.telegram_id,
        months=months,
    )

    # Проверяем что подписка была продлена
    refreshed_user = await session.get(User, user.id)
    assert refreshed_user.subscriptions[0].is_active
    assert user_schema.telegram_id == user.telegram_id
