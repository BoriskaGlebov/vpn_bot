import pytest
from enums.admin_enum import RoleEnum
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from users.schemas import SRoleOut

from api.admin.router import router as admin_router
from api.admin.services import AdminService
from api.users.models import User
from api.users.schemas import SRole, SUserOut

# --------------------------
# Фикстуры
# --------------------------


@pytest.fixture
async def test_app() -> FastAPI:
    """Создаем тестовое FastAPI приложение с подключением роутеров."""
    app = FastAPI()
    app.include_router(admin_router)
    return app


@pytest.fixture
async def mock_session():
    """Фиктивная асинхронная сессия базы данных."""

    class DummySession:
        async def execute(self, *args, **kwargs):
            return None

    return DummySession()


@pytest.fixture
def mock_admin_user() -> User:
    """Фиктивный админ."""
    return User(id=1, username="admin", telegram_id=999)


@pytest.fixture
def mock_service(monkeypatch):
    """Мокаем AdminService для теста get_user_by_telegram_id."""

    class MockAdminService:
        async def get_user_by_telegram_id(
            self, session: AsyncSession, telegram_id: int
        ):
            # Возвращаем фиктивного пользователя
            if telegram_id == 123:
                return SUserOut(
                    id=1,
                    telegram_id=123,
                    username="testuser",
                    first_name="Test",
                    last_name="User",
                    has_used_trial=False,
                    role=SRoleOut(id=1, name="admin"),  # Можно добавить фиктивную роль
                    subscriptions=[],
                    vpn_configs=[],
                    current_subscription=None,
                )
            else:
                from api.admin.services import UserNotFoundError

                raise UserNotFoundError(
                    f"Пользователь с telegram_id={telegram_id} не найден"
                )

    monkeypatch.setattr(
        "api.admin.dependencies.get_admin_service", lambda: MockAdminService()
    )


@pytest.fixture
def override_dependencies(mock_session, mock_admin_user, mock_service):
    """Переопределяем зависимости FastAPI для теста."""
    from core.dependencies import get_session as original_get_session

    from api.admin.dependencies import check_admin_role as original_check_admin_role
    from api.admin.dependencies import get_admin_service as original_get_admin_service

    return {
        original_get_session: lambda: mock_session,
        original_check_admin_role: lambda: mock_admin_user,
        original_get_admin_service: lambda: mock_service,  # <-- возвращаем мок-сервис
    }
