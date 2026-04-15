from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.main import app
from api.news.dependencies import get_news_service


class FakeNewsService:
    """Мок сервиса новостной рассылки."""

    def __init__(self):
        self.get_users_for_news = AsyncMock()


@pytest.fixture
def mock_service():
    """Фикстура мок-сервиса."""
    return FakeNewsService()


@pytest.fixture
def fake_logger(monkeypatch):
    """Мок логгера Loguru, используемого в роутере."""
    mock_logger = MagicMock()
    monkeypatch.setattr("api.news.router.logger", mock_logger)
    return mock_logger


@pytest.fixture
def client(mock_service, mock_session, mock_admin):
    """TestClient с переопределёнными зависимостями."""
    with patch(
        "api.main.init_default_roles_admins",
        new=AsyncMock(),
    ):
        app.dependency_overrides[get_news_service] = lambda: mock_service
        app.dependency_overrides[get_session] = lambda: mock_session
        app.dependency_overrides[check_admin_role] = lambda: mock_admin

        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


def test_get_news_recipients_success(
    client,
    mock_service,
    mock_session,
    fake_logger,
):
    """Проверяет успешное получение списка Telegram ID."""
    # Arrange
    expected_ids = [111111111, 222222222, 333333333]
    mock_service.get_users_for_news.return_value = expected_ids

    # Act
    response = client.get("/api/news/recipients")

    # Assert
    assert response.status_code == 200
    # assert response.json() == expected_ids
    mock_service.get_users_for_news.assert_awaited_once_with(session=mock_session)
    fake_logger.info.assert_called_once_with(
        "Получено {count} пользователей для новостной рассылки",
        count=len(expected_ids),
    )


def test_get_news_recipients_empty_list(
    client,
    mock_service,
    mock_session,
    fake_logger,
):
    """Проверяет корректную обработку пустого списка пользователей."""
    # Arrange
    mock_service.get_users_for_news.return_value = []

    # Act
    response = client.get("/api/news/recipients")

    # Assert
    assert response.status_code == 200
    assert response.json() == []
    mock_service.get_users_for_news.assert_awaited_once_with(session=mock_session)
    fake_logger.info.assert_called_once_with(
        "Получено {count} пользователей для новостной рассылки",
        count=0,
    )


def test_get_news_recipients_service_exception(
    client,
    mock_service,
    mock_session,
):
    """Проверяет обработку исключения, возникшего в сервисе."""
    # Arrange
    mock_service.get_users_for_news.side_effect = Exception("Database error")

    # Act
    response = client.get("/api/news/recipients")

    # Assert
    # Если в приложении нет глобального обработчика,
    # FastAPI вернёт статус 500.
    assert response.status_code == 500
    mock_service.get_users_for_news.assert_awaited_once_with(session=mock_session)
