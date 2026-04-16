from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from api.core.dependencies import get_current_user, get_session
from api.main import app
from api.referrals.dependencies import get_referral_service
from api.referrals.services import ReferralService


@pytest.fixture
def mock_referral_service():
    service = MagicMock(spec=ReferralService)

    service.register_referral = AsyncMock()
    service.grant_referral_bonus = AsyncMock(return_value=(True, 123))

    return service


@pytest.fixture
def client(mock_referral_service, session, mock_admin):
    with patch(
        "api.main.init_default_roles_admins",
        new=AsyncMock(),
    ):
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: mock_admin
        app.dependency_overrides[get_referral_service] = lambda: mock_referral_service

        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


def test_register_referral_success(client, mock_referral_service):
    payload = {
        "inviter_telegram_id": 111,
        "invited_user_id": 222,
    }

    with (
        patch(
            "api.referrals.router.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=MagicMock(id=2)),
        ),
        patch(
            "api.referrals.router.UserMapper.to_schema",
            new=AsyncMock(
                return_value=MagicMock(
                    id=2,
                    telegram_id=222,
                    has_used_trial=False,
                )
            ),
        ),
    ):
        response = client.post("/api/referrals/register", json=payload)

    assert response.status_code == 201


def test_register_referral_user_not_found(client):
    payload = {
        "inviter_telegram_id": 111,
        "invited_user_id": 999,
    }

    with patch(
        "api.referrals.router.UserDAO.find_one_or_none",
        new=AsyncMock(return_value=None),
    ):
        response = client.post("/api/referrals/register", json=payload)

    assert response.status_code == 404


def test_grant_bonus_success(client, mock_referral_service):
    payload = {
        "invited_user_id": 222,
        "months": 2,
    }
    with (
        patch(
            "api.referrals.router.UserDAO.find_one_or_none",
            new=AsyncMock(return_value=MagicMock(id=2)),
        ),
        patch(
            "api.referrals.router.UserMapper.to_schema",
            new=AsyncMock(
                return_value=MagicMock(
                    id=2,
                    telegram_id=222,
                    has_used_trial=False,
                )
            ),
        ),
    ):
        response = client.post("/api/referrals/bonus", json=payload)

        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["inviter_telegram_id"] == 123

        mock_referral_service.grant_referral_bonus.assert_awaited_once()


def test_grant_bonus_user_not_found(client):
    payload = {
        "invited_user_id": 999,
        "months": 1,
    }

    with patch(
        "api.referrals.router.UserDAO.find_one_or_none",
        new=AsyncMock(return_value=None),
    ):
        response = client.post("/api/referrals/bonus", json=payload)

    assert response.status_code == 404
