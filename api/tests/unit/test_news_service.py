from unittest.mock import MagicMock

import pytest
from loguru import logger as real_logger

from api.news.services import NewsService


@pytest.fixture
def fake_logger(monkeypatch):
    """Мок логгера Loguru, используемого в NewsService."""
    mock_logger = MagicMock(spec=real_logger)
    monkeypatch.setattr("api.news.services.logger", mock_logger)
    return mock_logger


@pytest.fixture
def news_service() -> NewsService:
    """Фикстура для создания экземпляра сервиса."""
    return NewsService()


@pytest.mark.asyncio
async def test_get_users_for_news_returns_user_ids(
    news_service,
    mock_session,
    mock_execute_result,
):
    """Проверяет, что метод возвращает список Telegram ID пользователей."""
    # Arrange
    expected_ids = [111111111, 222222222, 333333333]
    mock_execute_result.scalars.return_value.all.return_value = expected_ids
    mock_session.execute.return_value = mock_execute_result

    # Act
    result = await news_service.get_users_for_news(mock_session)

    # Assert
    assert result == expected_ids
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_users_for_news_returns_empty_list(
    news_service,
    mock_session,
    mock_execute_result,
):
    """Проверяет, что метод корректно обрабатывает отсутствие пользователей."""
    # Arrange
    mock_execute_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_execute_result

    # Act
    result = await news_service.get_users_for_news(mock_session)

    # Assert
    assert result == []
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_users_for_news_logs_message(
    news_service,
    mock_session,
    mock_execute_result,
    fake_logger,
):
    """Проверяет, что метод логирует успешное получение пользователей."""
    # Arrange
    expected_ids = [123]
    mock_execute_result.scalars.return_value.all.return_value = expected_ids
    mock_session.execute.return_value = mock_execute_result

    # Act
    result = await news_service.get_users_for_news(mock_session)

    # Assert: проверяем возвращаемое значение
    assert result == expected_ids

    # Assert: проверяем вызов логгера
    fake_logger.info.assert_called_once_with("Получил id пользователей для рассылки.")
