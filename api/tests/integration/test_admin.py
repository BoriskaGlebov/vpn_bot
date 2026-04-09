import pytest
from httpx import ASGITransport, AsyncClient

# --------------------------
# Тесты
# --------------------------


@pytest.mark.asyncio
async def test_get_user_success(test_app, override_dependencies):
    """Проверка успешного получения пользователя."""
    for dep, value in override_dependencies.items():
        test_app.dependency_overrides[dep] = value
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/admin/users/123")

    assert response.status_code == 200
    data = response.json()
    assert data["telegram_id"] == 123
    assert data["username"] == "testuser"


@pytest.mark.asyncio
async def test_get_user_not_found(test_app, override_dependencies):
    """Проверка обработки случая, когда пользователь не найден."""
    for dep, value in override_dependencies.items():
        test_app.dependency_overrides[dep] = value
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/admin/users/999")  # Пользователь не существует

    assert response.status_code == 404
    assert "detail" in response.json()
