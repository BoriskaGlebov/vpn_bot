from unittest.mock import AsyncMock

import pytest

from bot.admin.schemas import SYearIncome
from bot.admin.services import AdminService
from shared.enums.admin_enum import RoleEnum


@pytest.mark.asyncio
async def test_get_user_by_telegram_id(mock_admin_adapter, user_out):
    mock_admin_adapter.get_user_by_telegram_id.return_value = user_out
    service = AdminService(adapter=mock_admin_adapter)

    user = await service.get_user_by_telegram_id(123456)

    mock_admin_adapter.get_user_by_telegram_id.assert_awaited_once_with(123456)
    assert user.telegram_id == 123456
    assert user.username == "test_user"


@pytest.mark.asyncio
async def test_get_users_by_filter(mock_admin_adapter, user_out):
    mock_admin_adapter.get_users.return_value = [user_out, user_out]
    service = AdminService(adapter=mock_admin_adapter)

    users = await service.get_users_by_filter(RoleEnum.USER)

    mock_admin_adapter.get_users.assert_awaited_once_with(RoleEnum.USER)
    assert len(users) == 2
    assert all(u.telegram_id == 123456 for u in users)


@pytest.mark.asyncio
async def test_change_user_role(mock_admin_adapter, user_out):
    mock_admin_adapter.change_user_role.return_value = user_out
    service = AdminService(adapter=mock_admin_adapter)

    user = await service.change_user_role(123456, RoleEnum.ADMIN)

    mock_admin_adapter.change_user_role.assert_awaited_once()
    called_payload = mock_admin_adapter.change_user_role.call_args[0][0]
    assert called_payload.telegram_id == 123456
    assert called_payload.role_name == RoleEnum.ADMIN
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_extend_user_subscription(mock_admin_adapter, user_out):
    mock_admin_adapter.extend_subscription.return_value = user_out
    service = AdminService(adapter=mock_admin_adapter)

    user = await service.extend_user_subscription(123456, 3)

    mock_admin_adapter.extend_subscription.assert_awaited_once()
    called_payload = mock_admin_adapter.extend_subscription.call_args[0][0]
    assert called_payload.telegram_id == 123456
    assert called_payload.months == 3
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_year_income_calls_adapter(mocker):
    """Проверяет вызов adapter.year_income."""
    expected = SYearIncome(year_income=1000)

    adapter = mocker.Mock()
    adapter.year_income = AsyncMock(return_value=expected)

    service = AdminService(adapter)

    await service.year_income()

    adapter.year_income.assert_awaited_once()


@pytest.mark.asyncio
async def test_year_income_returns_result(mocker):
    """Проверяет возврат результата адаптера."""
    expected = SYearIncome(year_income=1000)

    adapter = mocker.Mock()
    adapter.year_income = AsyncMock(return_value=expected)

    service = AdminService(adapter)

    result = await service.year_income()

    assert result == expected
    assert result.year_income == 1000
