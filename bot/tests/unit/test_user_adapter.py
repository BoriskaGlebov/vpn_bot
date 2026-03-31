# tests/test_users_adapter.py

from typing import Any

import httpx
import pytest

from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUser, SUserOut


@pytest.mark.asyncio
async def test_register_new_user(
    api_client: Any,
    user_in: SUser,
    user_out: SUserOut,
) -> None:
    """Проверяет регистрацию нового пользователя (HTTP 201).

    Сценарий:
        - API возвращает статус 201;
        - пользователь считается новым.

    Проверяется:
        - корректная десериализация ответа;
        - совпадение telegram_id;
        - флаг is_new == True.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        # Проверяем корректность запроса
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
async def test_register_existing_user(
    api_client: Any,
    user_in: SUser,
    user_out: SUserOut,
) -> None:
    """Проверяет сценарий существующего пользователя (HTTP 200).

    Сценарий:
        - API возвращает статус 200;
        - пользователь уже существует.

    Проверяется:
        - корректное преобразование ответа;
        - флаг is_new == False.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
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
async def test_register_http_error(
    api_client: Any,
    user_in: SUser,
) -> None:
    """Проверяет обработку HTTP ошибки от API.

    Сценарий:
        - API возвращает ошибку (например, 400);
        - клиент должен выбросить исключение.

    Проверяется:
        - ошибка не подавляется;
        - вызывающий код получает исключение.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=400,
            json={"error": "bad request"},
        )

    client = await api_client(handler)
    adapter = UsersAPIAdapter(client)

    with pytest.raises(Exception):
        await adapter.register(user_in)
