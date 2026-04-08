from unittest.mock import AsyncMock

from api.users.schemas import SRoleOut, SUserOut


def make_user():
    return SUserOut(
        id=1,
        telegram_id=123,
        username="test",
        first_name="Test",
        last_name="User",
        has_used_trial=False,
        role=SRoleOut(id=1, name="admin", description=None),
        subscriptions=[],
        vpn_configs=[],
        current_subscription=None,
    )


def test_get_user_success(client, mock_service):
    user = make_user()

    mock_service.get_user_by_telegram_id = AsyncMock(return_value=user)

    response = client.get("/admin/users/123")

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 123


def test_get_user_not_found(client, mock_service):
    from api.app_error.base_error import UserNotFoundError

    mock_service.get_user_by_telegram_id = AsyncMock(
        side_effect=UserNotFoundError(tg_id=123)
    )

    response = client.get("/admin/users/123")

    assert response.status_code == 404


from shared.enums.admin_enum import RoleEnum


def test_get_users(client, mock_service):
    users = [make_user(), make_user()]

    mock_service.get_users_by_filter = AsyncMock(return_value=users)

    response = client.get("/admin/users", params={"filter_type": RoleEnum.ADMIN.value})

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_change_user_role_success(client, mock_service):
    user = make_user()

    mock_service.change_user_role = AsyncMock(return_value=user)

    payload = {
        "telegram_id": 123,
        "role_name": "admin",
    }

    response = client.patch("/admin/users/role", json=payload)

    assert response.status_code == 200
    assert response.json()["role"]["name"] == "admin"


def test_change_user_role_not_found(client, mock_service):
    from api.app_error.base_error import UserNotFoundError

    mock_service.change_user_role = AsyncMock(side_effect=UserNotFoundError(tg_id=123))

    payload = {
        "telegram_id": 123,
        "role_name": "admin",
    }

    response = client.patch("/admin/users/role", json=payload)

    assert response.status_code == 404


def test_extend_subscription_success(client, mock_service):
    user = make_user()

    mock_service.extend_user_subscription = AsyncMock(return_value=user)

    payload = {
        "telegram_id": 123,
        "months": 3,
    }

    response = client.patch("/admin/users/subscription", json=payload)

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 123


def test_extend_subscription_validation_error(client):
    payload = {
        "telegram_id": 123,
        "months": 0,  # invalid (ge=1)
    }

    response = client.patch("/admin/users/subscription", json=payload)

    assert response.status_code == 422
