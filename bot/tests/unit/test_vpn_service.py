from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import (
    SubscriptionNotFoundError,
    VPNConfigDeletionFailedError,
    VPNLimitError,
)
from bot.users.schemas import SVPNConfigOut
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
        Path("/tmp/test.vpn"),
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

    file_path1, file_path2, pub_key = await service.generate_user_config(
        tg_user=tg_user,
        ssh_client_factory=ssh_factory,
        server_info=server_info,
    )

    assert file_path1.name == "test.conf"
    assert file_path2.name == "test.vpn"
    assert pub_key == "pubkey123"

    api_adapter.check_limit.assert_awaited_once_with(tg_id=123)

    user_adapter.register.assert_awaited_once()

    ssh_instance.add_new_user_gen_config.assert_awaited_once_with(file_name="test_user")

    api_adapter.add_config.assert_awaited_once_with(
        tg_id=123456,
        file_name="test.conf / test.vpn",
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
        Path("/tmp/test.vpn"),
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

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = SimpleNamespace(is_active=True, end_date=None)

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
async def test_generate_xray_subscription_no_active_subscription_rejected(
    mocker, tg_user
):
    """Без активной подписки XRay-конфиг не выдаётся.

    Регрессия на баг: 3x-ui трактует expiryTime=0 как "бессрочно", поэтому
    отсутствие активной подписки должно явно отклоняться, а не молча
    приводить к days_left=0 и бессрочному доступу.
    """
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = None

    mocker.patch.object(service, "_limit_and_user_inf", return_value=user)

    with pytest.raises(SubscriptionNotFoundError):
        await service.generate_xray_subscription(tg_user=tg_user, location="ru")

    xray_adapter.add_new_config.assert_not_called()
    api_adapter.add_config.assert_not_called()


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
    user.current_subscription = SimpleNamespace(is_active=True, end_date=None)

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
    user.current_subscription = SimpleNamespace(is_active=True, end_date=None)

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
    user.current_subscription = SimpleNamespace(is_active=True, end_date=future_date)

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


@pytest.mark.asyncio
async def test_delete_from_ssh_nodes_broken_pipe_is_recoverable(mocker):
    """BrokenPipeError не должен прерывать перебор нод/версий контейнера.

    Регрессия: на проде `docker exec` в контейнер несуществующей версии
    (нода реально запускает только одну из старой/новой версии) рвёт
    shell-сессию раньше, чем команда успевает уйти — `full_delete_user`
    падает с `BrokenPipeError`, а не доменной `AmneziaError`. До фикса это
    исключение не ловилось и улетало пользователю как "unexpected_error".
    """
    from bot.core.config import settings_bot

    fake_node = SimpleNamespace(
        host="example.com",
        username="root",
        use_local=True,
        location_prefix="ru_",
        container="amnezia-awg2",
        container_old="amnezia-awg",
    )
    mocker.patch.object(settings_bot.vpn, "nodes", {"main": fake_node})

    ssh_instance = mocker.AsyncMock()
    ssh_instance.full_delete_user = mocker.AsyncMock(
        side_effect=BrokenPipeError("Channel not open for sending")
    )
    ssh_client_cls_mock = mocker.Mock(__name__="AsyncSSHClientWG")
    ssh_client_cls_mock.return_value.__aenter__ = mocker.AsyncMock(
        return_value=ssh_instance
    )
    ssh_client_cls_mock.return_value.__aexit__ = mocker.AsyncMock(return_value=False)

    mocker.patch("bot.vpn.services.AsyncSSHClientWG", ssh_client_cls_mock)
    mocker.patch("bot.vpn.services.AsyncSSHClientWG2", ssh_client_cls_mock)

    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    service = VPNService(api_adapter, user_adapter, xray_registry)

    deleted, had_error = await service._delete_from_ssh_nodes("PUBKEY", "conf1.conf")

    assert deleted is False
    assert had_error is True
    # Обе версии клиента должны быть опробованы, а не только первая.
    assert ssh_instance.full_delete_user.await_count == 2


@pytest.mark.asyncio
async def test_delete_from_ssh_nodes_skips_old_container_when_not_configured(mocker):
    """Нода без `container_old` не должна давать гарантированный "промах".

    Регрессия: конфиг был реально удалён на внешних сервисах, но метод
    всё равно возвращал `had_error=True` и блокировал очистку записи в БД
    — код вслепую пробовал старую версию контейнера (`AsyncSSHClientWG`)
    даже на нодах, где `container_old` не задан и такого контейнера
    никогда не было. Теперь такая нода пробуется только один раз — только
    новым клиентом с реально настроенным именем контейнера.
    """
    from bot.core.config import settings_bot

    fake_node = SimpleNamespace(
        host="example.com",
        username="root",
        use_local=True,
        location_prefix="fi_",
        container="amnezia-awg2",
        container_old=None,
    )
    mocker.patch.object(settings_bot.vpn, "nodes", {"fi": fake_node})

    ssh_instance = mocker.AsyncMock()
    ssh_instance.full_delete_user = mocker.AsyncMock(return_value=False)
    ssh_client_cls_mock = mocker.Mock(__name__="AsyncSSHClientWG2")
    ssh_client_cls_mock.return_value.__aenter__ = mocker.AsyncMock(
        return_value=ssh_instance
    )
    ssh_client_cls_mock.return_value.__aexit__ = mocker.AsyncMock(return_value=False)

    mocker.patch("bot.vpn.services.AsyncSSHClientWG2", ssh_client_cls_mock)

    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    service = VPNService(api_adapter, user_adapter, xray_registry)

    deleted, had_error = await service._delete_from_ssh_nodes("PUBKEY", "conf1.conf")

    assert deleted is False
    assert had_error is False
    ssh_client_cls_mock.assert_called_once_with(
        host="example.com",
        username="root",
        container="amnezia-awg2",
        use_local=True,
        location_prefix="fi_",
    )


@pytest.mark.asyncio
async def test_delete_user_config_found_via_ssh(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    mocker.patch.object(service, "_delete_from_ssh_nodes", return_value=(True, False))
    delete_xray_mock = mocker.patch.object(service, "_delete_from_xray")

    config = SVPNConfigOut(id=1, file_name="conf1.conf", pub_key="PUBKEY")

    result = await service.delete_user_config(tg_id=123, config=config)

    assert result is True
    delete_xray_mock.assert_not_called()
    api_adapter.delete_config.assert_awaited_once_with(
        file_name="conf1.conf", pub_key="PUBKEY", tg_id=123
    )


@pytest.mark.asyncio
async def test_delete_user_config_found_via_xray_fallback(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    mocker.patch.object(service, "_delete_from_ssh_nodes", return_value=(False, False))
    mocker.patch.object(service, "_delete_from_xray", return_value=(True, False))

    config = SVPNConfigOut(id=1, file_name="conf1.conf", pub_key='["cfg1"]')

    result = await service.delete_user_config(tg_id=123, config=config)

    assert result is True
    api_adapter.delete_config.assert_awaited_once_with(
        file_name="conf1.conf", pub_key='["cfg1"]', tg_id=123
    )


@pytest.mark.asyncio
async def test_delete_user_config_not_found_anywhere_still_cleans_db(mocker):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    mocker.patch.object(service, "_delete_from_ssh_nodes", return_value=(False, False))
    mocker.patch.object(service, "_delete_from_xray", return_value=(False, False))

    config = SVPNConfigOut(id=1, file_name="conf1.conf", pub_key="PUBKEY")

    result = await service.delete_user_config(tg_id=123, config=config)

    assert result is False
    api_adapter.delete_config.assert_awaited_once_with(
        file_name="conf1.conf", pub_key="PUBKEY", tg_id=123
    )


@pytest.mark.asyncio
async def test_delete_user_config_raises_on_connection_error(mocker):
    """Если было реальное сетевое/API-соединение — не трогаем БД, поднимаем ошибку."""
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    mocker.patch.object(service, "_delete_from_ssh_nodes", return_value=(False, True))
    mocker.patch.object(service, "_delete_from_xray", return_value=(False, False))

    config = SVPNConfigOut(id=1, file_name="conf1.conf", pub_key="PUBKEY")

    with pytest.raises(VPNConfigDeletionFailedError):
        await service.delete_user_config(tg_id=123, config=config)

    api_adapter.delete_config.assert_not_called()
