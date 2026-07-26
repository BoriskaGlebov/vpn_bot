from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from api.core.dependencies import get_current_user, get_session
from api.tests.conftest import fake_user
from api.vpn.dependencies import get_vpn_service
from api.vpn.services import VPNService


@pytest.fixture
def service_mock():
    return MagicMock(spec=VPNService)


@pytest.fixture
def client(make_client, service_mock):
    """TestClient с переопределёнными зависимостями роутера VPN."""
    with make_client(
        {
            get_vpn_service: lambda: service_mock,
            get_session: lambda: AsyncMock(),
            get_current_user: fake_user,
        }
    ) as c:
        yield c


def test_vpn_check_limit_success(client, service_mock):
    """Лимит устройств не исчерпан -> can_add=True."""
    service_mock.check_limit.return_value = {
        "can_add": True,
        "limit": 5,
        "current": 2,
    }

    response = client.get("/api/vpn/limit?tg_id=123")

    assert response.status_code == 200
    assert response.json()["can_add"] is True

    service_mock.check_limit.assert_awaited_once_with(
        session=ANY,
        tg_id=123,
    )


def test_vpn_add_config_success(client, service_mock):
    """Добавление VPN-конфига возвращает 201 с данными конфига."""
    service_mock.add_config.return_value = {
        "file_name": "test.conf",
        "pub_key": "key",
    }

    payload = {
        "tg_id": 123,
        "file_name": "test.conf",
        "pub_key": "key",
    }

    response = client.post("/api/vpn/config", json=payload)

    assert response.status_code == 201
    assert response.json()["file_name"] == "test.conf"

    service_mock.add_config.assert_awaited_once_with(
        session=ANY,
        tg_id=123,
        file_name="test.conf",
        pub_key="key",
    )


def test_vpn_delete_config_success(client, service_mock):
    """Удаление VPN-конфига возвращает количество удалённых записей."""
    service_mock.delete_config.return_value = 1

    payload = {
        "file_name": "test.conf",
        "pub_key": "key",
    }

    response = client.request(
        "DELETE",
        "/api/vpn/config",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["deleted"] == 1

    service_mock.delete_config.assert_awaited_once_with(
        session=ANY,
        file_name="test.conf",
        pub_key="key",
    )


def test_vpn_check_limit_false(client, service_mock):
    """Лимит устройств исчерпан -> can_add=False."""
    service_mock.check_limit.return_value = {
        "can_add": False,
        "limit": 1,
        "current": 1,
    }

    response = client.get("/api/vpn/limit?tg_id=123")

    assert response.status_code == 200
    assert response.json()["can_add"] is False
