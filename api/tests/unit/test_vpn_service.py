from unittest.mock import AsyncMock, MagicMock

import pytest

from api.app_error.base_error import UserNotFoundError
from api.vpn.services import VPNService


@pytest.fixture
def service():
    return VPNService()


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def user():
    sub = MagicMock()
    sub.type = "pro"

    u = MagicMock()
    u.id = 1
    u.current_subscription = sub
    u.vpn_configs = [MagicMock(), MagicMock()]  # 2 конфигa
    return u


@pytest.mark.asyncio
async def test_check_limit_ok(service, session, monkeypatch, user):
    monkeypatch.setattr(
        "api.vpn.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    monkeypatch.setattr(
        "api.vpn.services.VPNConfigDAO.can_add_config",
        AsyncMock(return_value=True),
    )

    monkeypatch.setattr(
        "api.vpn.services.DEVICE_LIMITS",
        {"pro": 5},
    )

    result = await service.check_limit(session=session, tg_id=123)

    assert result.can_add is True
    assert result.limit == 5
    assert result.current == 2


@pytest.mark.asyncio
async def test_check_limit_user_not_found(service, session, monkeypatch):
    monkeypatch.setattr(
        "api.vpn.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=None),
    )

    with pytest.raises(UserNotFoundError):
        await service.check_limit(session=session, tg_id=123)


@pytest.mark.asyncio
async def test_add_config_ok(service, session, monkeypatch, user):
    monkeypatch.setattr(
        "api.vpn.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=user),
    )

    add_mock = AsyncMock()
    monkeypatch.setattr(
        "api.vpn.services.VPNConfigDAO.add_config",
        add_mock,
    )

    result = await service.add_config(
        session=session,
        tg_id=123,
        file_name="test.conf",
        pub_key="pubkey",
    )

    add_mock.assert_awaited_once()

    assert result.file_name == "test.conf"
    assert result.pub_key == "pubkey"


@pytest.mark.asyncio
async def test_add_config_user_not_found(service, session, monkeypatch):
    monkeypatch.setattr(
        "api.vpn.services.UserDAO.find_one_or_none",
        AsyncMock(return_value=None),
    )

    with pytest.raises(UserNotFoundError):
        await service.add_config(
            session=session,
            tg_id=123,
            file_name="x.conf",
            pub_key="key",
        )


@pytest.mark.asyncio
async def test_delete_config(service, session, monkeypatch):
    delete_mock = AsyncMock(return_value=1)

    monkeypatch.setattr(
        "api.vpn.services.VPNConfigDAO.delete",
        delete_mock,
    )

    result = await service.delete_config(
        file_name="test.conf",
        session=session,
        pub_key="key",
    )

    delete_mock.assert_awaited_once()
    assert result == 1
