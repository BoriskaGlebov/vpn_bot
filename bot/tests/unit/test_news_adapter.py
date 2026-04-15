import httpx
import pytest

from bot.app_error.api_error import APIClientError
from bot.news.adapter import NewsAPIAdapter


@pytest.mark.asyncio
async def test_get_recipients_success(api_client) -> None:
    """Тест успешного получения списка получателей.

    Проверяет:
        1. Метод `get_recipients` корректно возвращает список Telegram ID.
        2. Числовые строки конвертируются в int.
    """

    async def handler(request):
        return httpx.Response(status_code=200, json=[1, "2", 3])

    client = await api_client(handler)
    adapter = NewsAPIAdapter(client)

    result = await adapter.get_recipients()

    assert result == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_recipients_not_list(api_client) -> None:
    """Тест обработки некорректного формата ответа API.

    Проверяет, что если API вернул не список, метод выбрасывает APIClientError.
    """

    async def handler(request):
        return httpx.Response(status_code=200, json={"invalid": "data"})

    client = await api_client(handler)
    adapter = NewsAPIAdapter(client)

    with pytest.raises(APIClientError, match="Некорректный формат"):
        await adapter.get_recipients()


@pytest.mark.asyncio
async def test_get_recipients_invalid_ids(api_client) -> None:
    """Тест обработки некорректных ID получателей.

    Проверяет, что если в списке есть элементы, которые не приводятся к int,
    метод выбрасывает APIClientError.
    """

    async def handler(request):
        return httpx.Response(status_code=200, json=[1, "abc", 3])

    client = await api_client(handler)
    adapter = NewsAPIAdapter(client)

    with pytest.raises(APIClientError, match="Некорректные данные"):
        await adapter.get_recipients()


@pytest.mark.asyncio
async def test_get_recipients_none(api_client) -> None:
    """Тест обработки ответа API со значением None.

    Проверяет, что метод выбрасывает APIClientError при отсутствии списка получателей.
    """

    async def handler(request):
        return httpx.Response(status_code=200, json=None)

    client = await api_client(handler)
    adapter = NewsAPIAdapter(client)

    with pytest.raises(APIClientError):
        await adapter.get_recipients()
