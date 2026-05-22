import datetime
import json
from unittest.mock import AsyncMock

import pytest
from httpx import Response

from bot.admin.adapter import AdminAPIAdapter
from bot.admin.schemas import SChangeRole, SExtendSubscription, SYearIncome
from bot.users.schemas import SUserOut
from shared.enums.admin_enum import RoleEnum


@pytest.mark.asyncio
async def test_get_user_by_telegram_id(api_client, user_response):
    async def handler(request):

        assert request.url.path == "/admin/users/123456"
        return Response(200, json=user_response)

    client = await api_client(handler)
    adapter = AdminAPIAdapter(client)

    user = await adapter.get_user_by_telegram_id(telegram_id=123456)

    assert user.telegram_id == 123456
    assert user.username == "test_user"
    assert user.role.name == "user"
    assert isinstance(user, SUserOut)


@pytest.mark.asyncio
async def test_get_users(api_client, user_response):
    async def handler(request):
        assert request.url.path == "/admin/users"
        assert request.url.params["filter_type"] == "user"
        # Возвращаем список пользователей в формате SUserOut
        return Response(200, json=[user_response, user_response])

    client = await api_client(handler)
    adapter = AdminAPIAdapter(client)

    users = await adapter.get_users(filter_type=RoleEnum.USER)

    assert len(users) == 2
    assert all(isinstance(u, SUserOut) for u in users)
    assert users[0].telegram_id == 123456
    assert users[1].role.name == "user"


@pytest.mark.asyncio
async def test_change_user_role(api_client, user_response):
    async def handler(request):
        body = json.loads(request.content)
        assert body["telegram_id"] == 123456
        assert body["role_name"] == "admin"
        # Возвращаем корректный JSON с обновлённой ролью
        updated_user = dict(user_response)
        updated_user["role"] = {
            "id": 2,
            "name": "admin",
            "description": "Administrator",
        }
        return Response(200, json=updated_user)

    client = await api_client(handler)
    adapter = AdminAPIAdapter(client)

    payload = SChangeRole(telegram_id=123456, role_name=RoleEnum.ADMIN)
    user = await adapter.change_user_role(payload)

    assert isinstance(user, SUserOut)
    assert user.role.name == "admin"
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_extend_subscription(api_client, user_response):
    async def handler(request):
        body = json.loads(request.content)
        assert body["telegram_id"] == 123456
        assert body["months"] == 3
        # Возвращаем JSON без изменения роли
        return Response(200, json=user_response)

    client = await api_client(handler)
    adapter = AdminAPIAdapter(client)

    payload = SExtendSubscription(telegram_id=123456, months=3)
    user = await adapter.extend_subscription(payload)

    assert isinstance(user, SUserOut)
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_year_income_calls_client_with_current_year(mocker):
    """Проверяет корректный вызов client.get."""
    client = mocker.Mock()
    client.get = AsyncMock(return_value={"year_income": 1000})

    adapter = AdminAPIAdapter(client)

    await adapter.year_income()

    current_year = datetime.datetime.now().year

    client.get.assert_awaited_once_with(
        url="/admin/analytics/income",
        params={"year": current_year},
    )


@pytest.mark.asyncio
async def test_year_income_returns_validated_schema(mocker):
    """Проверяет возврат валидированной схемы."""
    response_data = {
        "year_income": 1000,
    }

    client = mocker.Mock()
    client.get = AsyncMock(return_value=response_data)

    adapter = AdminAPIAdapter(client)

    result = await adapter.year_income()

    assert isinstance(result, SYearIncome)
    assert result.year_income == 1000


@pytest.mark.asyncio
async def test_year_income_passes_response_to_model_validate(mocker):
    """Проверяет вызов model_validate."""
    response_data = {"year_income": 1000}

    client = mocker.Mock()
    client.get = AsyncMock(return_value=response_data)

    validate_mock = mocker.patch.object(
        SYearIncome,
        "model_validate",
        return_value="validated_result",
    )

    adapter = AdminAPIAdapter(client)

    result = await adapter.year_income()

    validate_mock.assert_called_once_with(response_data)
    assert result == "validated_result"
