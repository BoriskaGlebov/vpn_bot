from unittest.mock import AsyncMock

import pytest

from bot.app_error.api_error import APIClientError
from bot.news.adapter import NewsAPIAdapter
from bot.news.services import NewsService


@pytest.fixture
def news_adapter_mock() -> AsyncMock:
    """Мок NewsAPIAdapter для тестов сервиса новостной рассылки.

    Возвращает адаптер, который по умолчанию возвращает список пользователей [1, 2, 3].
    """
    mock_adapter = AsyncMock(spec=NewsAPIAdapter)
    mock_adapter.get_recipients.return_value = [1, 2, 3]
    return mock_adapter


@pytest.mark.asyncio
async def test_all_users_id_success(news_adapter_mock: AsyncMock) -> None:
    """Тест успешного получения всех пользователей.

    Проверяет, что сервис корректно вызывает адаптер и возвращает список Telegram ID.
    """
    service = NewsService(adapter=news_adapter_mock)

    result = await service.all_users_id()

    assert result == [1, 2, 3]
    news_adapter_mock.get_recipients.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_users_id_adapter_raises(news_adapter_mock: AsyncMock) -> None:
    """Тест обработки ошибки адаптера.

    Проверяет, что если адаптер выбрасывает APIClientError,
    сервис корректно пробрасывает это исключение дальше.
    """
    # Мокаем, чтобы метод выбрасывал исключение
    news_adapter_mock.get_recipients.side_effect = APIClientError("Ошибка API")

    service = NewsService(adapter=news_adapter_mock)

    with pytest.raises(APIClientError, match="Ошибка API"):
        await service.all_users_id()
