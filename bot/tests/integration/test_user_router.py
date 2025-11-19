import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.users.schemas import SUserOut
from bot.users.services import UserService


@pytest.mark.asyncio
@pytest.mark.users
async def test_register_new_user(user_service: UserService, session: AsyncSession):
    from aiogram.types import User as TgUser

    # Создаём тестового Telegram пользователя
    tg_user = TgUser(
        id=999999,
        username="testuser",
        is_bot=False,
        first_name="Test",
        last_name="User",
    )

    # Проверяем, что пользователь отсутствует в БД
    existing_user, created_flag = await user_service.register_or_get_user(
        session, tg_user
    )
    assert isinstance(existing_user, SUserOut)
    assert created_flag is True

    # Второй вызов должен вернуть существующего пользователя
    same_user, created_flag2 = await user_service.register_or_get_user(session, tg_user)
    assert same_user.telegram_id == tg_user.id
    assert created_flag2 is False


@pytest.mark.asyncio
@pytest.mark.users
async def test_register_admin_user(
    user_service: UserService, session: AsyncSession, test_admin_id: int
):
    from aiogram.types import User as TgUser

    # Создаём Telegram пользователя с ID администратора
    tg_user = TgUser(
        id=test_admin_id,
        username="adminuser",
        first_name="Admin",
        last_name="User",
        is_bot=False,
    )

    user, created = await user_service.register_or_get_user(session, tg_user)
    assert created is True
    # Проверяем роль
    assert user.role.name == "admin"


@pytest.mark.asyncio
@pytest.mark.users
async def test_get_existing_user(user_service: UserService, session: AsyncSession):
    from aiogram.types import User as TgUser

    tg_user = TgUser(
        id=1001, username="existing", is_bot=False, first_name="Exist", last_name="User"
    )

    # Сначала создаём пользователя
    await user_service.register_or_get_user(session, tg_user)

    # Получаем повторно
    user, created = await user_service.register_or_get_user(session, tg_user)
    assert created is False
    assert user.username == "existing"
