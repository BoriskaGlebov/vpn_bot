# tests/test_users_adapter.py
import httpx
import pytest

from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUserOut


@pytest.mark.asyncio
async def test_register_new_user(api_client, user_in, user_out):
    """Тест регистрации нового пользователя (201)."""

    async def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/api/users/register"

        return httpx.Response(
            status_code=201,
            json=user_out.model_dump(mode="json"),
        )

    client = await api_client(handler)
    adapter = UsersAPIAdapter(client)

    result, is_new = await adapter.register(user_in)

    assert isinstance(result, SUserOut)
    assert result.telegram_id == user_in.telegram_id
    assert is_new is True


@pytest.mark.asyncio
async def test_register_existing_user(api_client, user_in, user_out):
    """Тест когда пользователь уже существует (200)."""

    async def handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            json=user_out.model_dump(mode="json"),
        )

    client = await api_client(handler)
    adapter = UsersAPIAdapter(client)

    result, is_new = await adapter.register(user_in)

    assert result.id == user_out.id
    assert is_new is False


@pytest.mark.asyncio
async def test_register_http_error(api_client, user_in):
    async def handler(request: httpx.Request):
        return httpx.Response(status_code=400, json={"error": "bad request"})

    client = await api_client(handler)
    adapter = UsersAPIAdapter(client)

    with pytest.raises(Exception):
        await adapter.register(user_in)
