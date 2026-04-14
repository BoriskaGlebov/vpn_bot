from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.schemas import (
    SUser,
    SUserOut,
    SUserWithReferralStats,
)
from api.users.services import UserService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service() -> UserService:
    return UserService()


@pytest.fixture
def session() -> AsyncSession:
    return MagicMock(spec=AsyncSession)


# ---------- register_or_get_user ----------


@patch("api.users.services.UserMapper.to_schema", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_existing(
    mock_find_user,
    mock_to_schema,
    service,
    session,
):
    fake_user = MagicMock()
    mock_find_user.return_value = fake_user

    expected_schema = MagicMock(spec=SUserOut)
    mock_to_schema.return_value = expected_schema

    telegram_user = SUser(
        telegram_id=123,
        username="existing_user",
        first_name="Test",
        last_name="User",
    )

    result, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert result is expected_schema
    assert created is False

    mock_find_user.assert_awaited_once()
    mock_to_schema.assert_awaited_once_with(fake_user)


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_create_admin(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Создание администратора."""
    mock_find_user.return_value = None
    mock_settings.admin_ids = [999]

    fake_user = MagicMock()
    mock_add_user.return_value = fake_user

    expected_schema = MagicMock(spec=SUserOut)
    mock_to_schema.return_value = expected_schema

    telegram_user = SUser(
        telegram_id=999,
        username="admin_user",
        first_name="Admin",
        last_name="User",
    )

    result, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert created is True
    assert result == expected_schema

    # Проверяем, что была назначена роль admin
    args, kwargs = mock_add_user.await_args
    assert kwargs["values_role"].name == "admin"


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_create_regular_user(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Создание обычного пользователя."""
    mock_find_user.return_value = None
    mock_settings.admin_ids = []

    fake_user = MagicMock()
    mock_add_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(
        telegram_id=123,
        username="regular_user",
        first_name="Test",
        last_name="User",
    )

    _, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert created is True

    args, kwargs = mock_add_user.await_args
    assert kwargs["values_role"].name == "user"


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_guest_username(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Если username отсутствует, используется значение по умолчанию."""
    mock_find_user.return_value = None
    mock_settings.admin_ids = []

    fake_user = MagicMock()
    mock_add_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(
        telegram_id=555,
        username=None,
        first_name="Guest",
        last_name="User",
    )

    await service.register_or_get_user(session=session, telegram_user=telegram_user)

    args, kwargs = mock_add_user.await_args
    assert kwargs["values_user"].username == "Гость_555"


# ---------- get_user_with_referrals ----------


@patch(
    "api.users.services.UserMapper.to_schema_with_referrals",
    new_callable=AsyncMock,
)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_get_user_with_referrals_found(
    mock_find_user,
    mock_to_schema,
    service,
    session,
):
    """Пользователь найден."""
    fake_user = MagicMock()
    mock_find_user.return_value = fake_user

    expected_schema = MagicMock(spec=SUserWithReferralStats)
    mock_to_schema.return_value = expected_schema

    result = await service.get_user_with_referrals(
        session=session,
        telegram_id=123,
    )

    assert result == expected_schema
    mock_to_schema.assert_awaited_once_with(fake_user)


@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_get_user_with_referrals_not_found(
    mock_find_user,
    service,
    session,
):
    """Пользователь не найден."""
    mock_find_user.return_value = None

    result = await service.get_user_with_referrals(
        session=session,
        telegram_id=123,
    )

    assert result is None
