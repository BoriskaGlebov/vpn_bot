from unittest.mock import AsyncMock, patch

import pytest

from api.admin.services import AdminService
from api.app_error.base_error import RoleNotFoundError, UserNotFoundError
from shared.enums.admin_enum import RoleEnum


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def mock_user_dao_find():
    with patch(
        "api.users.dao.UserDAO.find_one_or_none", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_role_dao_find():
    with patch(
        "api.users.dao.RoleDAO.find_one_or_none", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_get_users_by_roles():
    with patch(
        "api.users.dao.UserDAO.get_users_by_roles", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_change_role():
    with patch("api.users.dao.UserDAO.change_role", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_extend_subscription():
    with patch(
        "api.users.dao.UserDAO.extend_subscription", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_user_mapper():
    with patch(
        "api.core.mapper.user_mapper.UserMapper.to_schema", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.mark.asyncio
async def test_get_user_by_telegram_id_success(
    session,
    mock_user_dao_find,
    mock_user_mapper,
):
    fake_user = object()
    fake_schema = object()

    mock_user_dao_find.return_value = fake_user
    mock_user_mapper.return_value = fake_schema

    result = await AdminService.get_user_by_telegram_id(session, 123)

    assert result == fake_schema
    mock_user_dao_find.assert_called_once()
    mock_user_mapper.assert_called_once_with(fake_user)


@pytest.mark.asyncio
async def test_get_user_by_telegram_id_not_found(
    session,
    mock_user_dao_find,
):
    mock_user_dao_find.return_value = None

    with pytest.raises(UserNotFoundError):
        await AdminService.get_user_by_telegram_id(session, 123)


@pytest.mark.asyncio
async def test_get_users_by_filter(
    session,
    mock_get_users_by_roles,
    mock_user_mapper,
):
    fake_users = [object(), object()]
    fake_schemas = ["u1", "u2"]

    mock_get_users_by_roles.return_value = fake_users
    mock_user_mapper.side_effect = fake_schemas

    result = await AdminService.get_users_by_filter(session, RoleEnum.ADMIN)

    assert result == fake_schemas
    mock_get_users_by_roles.assert_called_once_with(
        session=session,
        filter_type=RoleEnum.ADMIN.value,
    )
    assert mock_user_mapper.call_count == 2


@pytest.mark.asyncio
async def test_change_user_role_success(
    session,
    mock_user_dao_find,
    mock_role_dao_find,
    mock_change_role,
    mock_user_mapper,
):
    fake_user = object()
    fake_role = object()
    changed_user = object()
    fake_schema = object()

    mock_user_dao_find.return_value = fake_user
    mock_role_dao_find.return_value = fake_role
    mock_change_role.return_value = changed_user
    mock_user_mapper.return_value = fake_schema

    result = await AdminService.change_user_role(
        session,
        telegram_id=1,
        role_name=RoleEnum.ADMIN,
    )

    assert result == fake_schema
    mock_change_role.assert_called_once_with(
        session=session,
        user=fake_user,
        role=fake_role,
    )


@pytest.mark.asyncio
async def test_change_user_role_user_not_found(
    session,
    mock_user_dao_find,
):
    mock_user_dao_find.return_value = None

    with pytest.raises(UserNotFoundError):
        await AdminService.change_user_role(session, 1, RoleEnum.ADMIN)


@pytest.mark.asyncio
async def test_change_user_role_role_not_found(
    session,
    mock_user_dao_find,
    mock_role_dao_find,
):
    mock_user_dao_find.return_value = object()
    mock_role_dao_find.return_value = None

    with pytest.raises(RoleNotFoundError):
        await AdminService.change_user_role(session, 1, RoleEnum.ADMIN)


@pytest.mark.asyncio
async def test_extend_user_subscription_success(
    session,
    mock_user_dao_find,
    mock_extend_subscription,
    mock_user_mapper,
):
    fake_user = object()
    changed_user = object()
    fake_schema = object()

    mock_user_dao_find.return_value = fake_user
    mock_extend_subscription.return_value = changed_user
    mock_user_mapper.return_value = fake_schema

    result = await AdminService.extend_user_subscription(
        session,
        telegram_id=1,
        months=3,
    )

    assert result == fake_schema
    mock_extend_subscription.assert_called_once_with(
        session=session,
        user=fake_user,
        months=3,
    )


@pytest.mark.asyncio
async def test_extend_user_subscription_user_not_found(
    session,
    mock_user_dao_find,
):
    mock_user_dao_find.return_value = None

    with pytest.raises(UserNotFoundError):
        await AdminService.extend_user_subscription(session, 1, 3)
