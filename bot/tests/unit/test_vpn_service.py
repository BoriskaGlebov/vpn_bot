from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import VPNLimitError
from bot.users.schemas import SUser
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
)
from bot.vpn.services import VPNService


@pytest.mark.asyncio
async def test_generate_user_config_success(mocker, user_out):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    tg_user = SimpleNamespace(id=123)

    api_adapter.check_limit.return_value = SVPNCheckLimitResponse(
        can_add=True,
        limit=5,
        current=1,
    )

    user_adapter.register.return_value = (
        user_out,
        True,
    )

    ssh_instance = mocker.AsyncMock()

    ssh_instance.add_new_user_gen_config.return_value = (
        Path("/tmp/test.conf"),
        "pubkey123",
    )

    ssh_factory = mocker.Mock()

    ssh_factory.return_value.__aenter__ = mocker.AsyncMock(return_value=ssh_instance)
    ssh_factory.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

    server_info = SimpleNamespace(
        host="localhost",
        username="root",
        container="vpn",
        use_local=True,
        location_prefix="ru_",
    )

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    file_path, pub_key = await service.generate_user_config(
        tg_user=tg_user,
        ssh_client_factory=ssh_factory,
        server_info=server_info,
    )

    assert file_path.name == "test.conf"
    assert pub_key == "pubkey123"

    api_adapter.check_limit.assert_awaited_once_with(tg_id=123)

    user_adapter.register.assert_awaited_once()

    ssh_instance.add_new_user_gen_config.assert_awaited_once_with(file_name="test_user")

    api_adapter.add_config.assert_awaited_once_with(
        tg_id=123456,
        file_name="test.conf",
        pub_key="pubkey123",
    )


@pytest.mark.asyncio
async def test_generate_user_config_limit_reached(mocker, user_out):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    ssh_factory = mocker.Mock()

    tg_user = SimpleNamespace(id=123)

    api_adapter.check_limit.return_value = SVPNCheckLimitResponse(
        can_add=False,
        limit=1,
        current=1,
    )

    user_adapter.register.return_value = (
        user_out,
        True,
    )

    server_info = SimpleNamespace(
        host="localhost",
        username="root",
        container="vpn",
        use_local=True,
        location_prefix="ru_",
    )

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    with pytest.raises(VPNLimitError) as exc:
        await service.generate_user_config(
            tg_user=tg_user,
            ssh_client_factory=ssh_factory,
            server_info=server_info,
        )

    err = exc.value

    assert err.user_id == 123456
    assert err.limit == 1

    ssh_factory.assert_not_called()
    api_adapter.add_config.assert_not_called()


@pytest.mark.asyncio
async def test_generate_user_config_db_error_rollback(mocker, user_out):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    tg_user = SimpleNamespace(id=123)

    api_adapter.check_limit.return_value = SVPNCheckLimitResponse(
        can_add=True,
        limit=5,
        current=1,
    )

    user_adapter.register.return_value = (
        user_out,
        True,
    )

    ssh_instance = mocker.AsyncMock()

    ssh_instance.add_new_user_gen_config.return_value = (
        Path("/tmp/test.conf"),
        "pubkey123",
    )

    ssh_factory = mocker.Mock()

    ssh_factory.return_value.__aenter__ = mocker.AsyncMock(return_value=ssh_instance)

    ssh_factory.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

    api_adapter.add_config.side_effect = APIClientError("DB error")

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    server_info = SimpleNamespace(
        host="localhost",
        username="root",
        container="vpn",
        use_local=True,
        location_prefix="ru_",
    )

    with pytest.raises(APIClientError):
        await service.generate_user_config(
            tg_user=tg_user,
            ssh_client_factory=ssh_factory,
            server_info=server_info,
        )

    ssh_instance.full_delete_user.assert_awaited_once_with(public_key="pubkey123")


@pytest.mark.asyncio
async def test_generate_xray_subscription_success(mocker, tg_user):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()

    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {
            "sub_ids": ["sub123"],
            "config_ids": ["cfg1", "cfg2"],
        },
        "http://sub.url",
    )

    url = await service.generate_xray_subscription(
        tg_user=tg_user,
        location="ru",
    )

    assert url == "http://sub.url"

    xray_registry.get.assert_called_once_with(name="ru")

    api_adapter.add_config.assert_awaited_once_with(
        tg_id=123,
        file_name="sub123",
        pub_key='["cfg1", "cfg2"]',
    )


@pytest.mark.asyncio
async def test_generate_xray_subscription_empty_sub_ids(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()

    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    tg_user = SimpleNamespace(id=123)

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {"sub_ids": [], "config_ids": []},
        "http://sub.url",
    )

    with pytest.raises(RuntimeError):
        await service.generate_xray_subscription(
            tg_user=tg_user,
            location="ru",
        )

    api_adapter.add_config.assert_not_called()

    xray_registry.get.assert_called_once_with(name="ru")


@pytest.mark.asyncio
async def test_generate_xray_subscription_db_error_rollback(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()

    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    tg_user = SimpleNamespace(id=123)

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {
            "sub_ids": ["sub123"],
            "config_ids": ["cfg1", "cfg2"],
        },
        "http://sub.url",
    )

    api_adapter.add_config.side_effect = APIClientError("DB error")

    with pytest.raises(APIClientError):
        await service.generate_xray_subscription(
            tg_user=tg_user,
            location="ru",
        )

    xray_registry.get.assert_called_once_with(name="ru")

    xray_adapter.delete_config.assert_any_await(
        config_id="cfg1",
    )

    xray_adapter.delete_config.assert_any_await(
        config_id="cfg2",
    )

    assert xray_adapter.delete_config.await_count == 2


@pytest.mark.asyncio
async def test_generate_xray_subscription_success(mocker, tg_user):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {"sub_ids": ["sub123"], "config_ids": ["cfg1", "cfg2"]},
        "http://sub.url",
    )

    url = await service.generate_xray_subscription(
        tg_user=tg_user,
        location="ru",
    )

    assert url == "http://sub.url"

    xray_registry.get.assert_called_once_with(name="ru")

    api_adapter.add_config.assert_awaited_once_with(
        tg_id=123,
        file_name="sub123",
        pub_key='["cfg1", "cfg2"]',
    )


@pytest.mark.asyncio
async def test_generate_xray_subscription_empty_sub_ids(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    tg_user = SimpleNamespace(id=123)

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {"sub_ids": [], "config_ids": []},
        "http://sub.url",
    )

    with pytest.raises(RuntimeError):
        await service.generate_xray_subscription(
            tg_user=tg_user,
            location="ru",
        )

    api_adapter.add_config.assert_not_called()


@pytest.mark.asyncio
async def test_generate_xray_subscription_db_error_rollback(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    tg_user = SimpleNamespace(id=123)

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {"sub_ids": ["sub123"], "config_ids": ["cfg1", "cfg2"]},
        "http://sub.url",
    )

    api_adapter.add_config.side_effect = APIClientError("DB error")

    with pytest.raises(APIClientError):
        await service.generate_xray_subscription(
            tg_user=tg_user,
            location="ru",
        )

    xray_adapter.delete_config.assert_any_await(
        config_id="cfg1",
    )

    xray_adapter.delete_config.assert_any_await(
        config_id="cfg2",
    )

    assert xray_adapter.delete_config.await_count == 2


@pytest.mark.asyncio
async def test_generate_xray_subscription_days_calculation(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    tg_user = SimpleNamespace(id=123)

    service = VPNService(api_adapter, user_adapter, xray_registry)

    future_date = datetime.now().replace(year=datetime.now().year + 1)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = SimpleNamespace(end_date=future_date)

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    xray_adapter.add_new_config.return_value = (
        {"sub_ids": ["sub123"], "config_ids": []},
        "url",
    )

    await service.generate_xray_subscription(
        tg_user=tg_user,
        location="ru",
    )

    args = xray_adapter.add_new_config.await_args.kwargs

    assert args["tg_id"] == 123
    assert args["days"] > 300
