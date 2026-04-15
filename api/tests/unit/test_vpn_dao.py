from unittest.mock import AsyncMock, MagicMock

import pytest

from api.app_error.base_error import SubscriptionNotFoundError, VPNLimitError
from api.vpn.dao import VPNConfigDAO


@pytest.fixture
def session():
    """Фейковая AsyncSession"""
    return AsyncMock()


@pytest.fixture
def user():
    sub = MagicMock()
    sub.is_active = True
    sub.type = "pro"

    u = MagicMock()
    u.current_subscription = sub
    return u


@pytest.mark.asyncio
async def test_can_add_config_under_limit(session, monkeypatch, user):
    # user найден
    monkeypatch.setattr(
        "api.vpn.dao.UserDAO.find_one_or_none_by_id",
        AsyncMock(return_value=user),
    )

    # уже 0 конфиг
    session.scalar.return_value = 0

    result = await VPNConfigDAO.can_add_config(session, user_id=1)

    assert result is True


@pytest.mark.asyncio
async def test_can_add_config_over_limit(session, monkeypatch, user):
    monkeypatch.setattr(
        "api.vpn.dao.UserDAO.find_one_or_none_by_id",
        AsyncMock(return_value=user),
    )

    # лимит = 1 (подменяем константу)
    monkeypatch.setattr(
        "api.vpn.dao.DEVICE_LIMITS",
        {"pro": 1},
    )

    session.scalar.return_value = 2

    result = await VPNConfigDAO.can_add_config(session, user_id=1)

    assert result is False


@pytest.mark.asyncio
async def test_can_add_config_no_user(session, monkeypatch):
    monkeypatch.setattr(
        "api.vpn.dao.UserDAO.find_one_or_none_by_id",
        AsyncMock(return_value=None),
    )

    result = await VPNConfigDAO.can_add_config(session, user_id=1)

    assert result is False


@pytest.mark.asyncio
async def test_add_config_raises_limit(session, monkeypatch, user):
    monkeypatch.setattr(
        "api.vpn.dao.UserDAO.find_one_or_none_by_id",
        AsyncMock(return_value=user),
    )

    monkeypatch.setattr(
        "api.vpn.dao.DEVICE_LIMITS",
        {"pro": 0},
    )

    session.scalar.return_value = 5

    with pytest.raises(VPNLimitError):
        await VPNConfigDAO.add_config(
            session=session,
            user_id=1,
            file_name="test.conf",
            pub_key="key",
        )
