import json

import pytest
from httpx import Response

from bot.admin.adapter import AdminAPIAdapter
from bot.admin.schemas import SChangeRole, SExtendSubscription
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
