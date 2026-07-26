from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.core.dependencies import get_current_user, get_session
from api.referrals.dependencies import get_referral_service
from api.referrals.services import ReferralService


@pytest.fixture
def mock_referral_service():
    service = MagicMock(spec=ReferralService)

    service.register_referral = AsyncMock()
    service.grant_referral_bonus = AsyncMock(
        return_value=(
            True,
            123,
            "Бонус за подписчика предоставлен",
        )
    )

    return service


@pytest.fixture
def client(make_client, mock_referral_service, session, mock_admin):
    """TestClient с переопределёнными зависимостями роутера рефералов."""
    with make_client(
        {
            get_session: lambda: session,
            get_current_user: lambda: mock_admin,
            get_referral_service: lambda: mock_referral_service,
        }
    ) as c:
        yield c


def test_register_referral_success(client, mock_referral_service):
    """Регистрация реферала для существующего приглашённого пользователя -> 201."""
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
    """Приглашённый пользователь не найден в БД -> 404."""
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
    """Начисление реферального бонуса -> 200 с деталями начисления."""
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
        assert data["message"] == "Бонус за подписчика предоставлен"

        mock_referral_service.grant_referral_bonus.assert_awaited_once()


def test_grant_bonus_user_not_found(client):
    """Приглашённый пользователь не найден в БД -> 404."""
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
