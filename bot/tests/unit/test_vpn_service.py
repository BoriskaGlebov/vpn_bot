from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import (
    SubscriptionNotFoundError,
    VPNConfigDeletionFailedError,
    VPNLimitError,
)
from bot.app_error.schema import ErrorDetail
from bot.users.schemas import SVPNConfigOut
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
)
from bot.vpn.services import VPNService
from bot.vpn.utils.amnezia_exceptions import AmneziaSSHError


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
        Path("/tmp/test.png"),
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
        protocol_version="v2",
    )

    service = VPNService(
        adapter=api_adapter,
        user_adapter=user_adapter,
        xray_registry=xray_registry,
    )

    file_path1, file_path2, file_path3, pub_key = await service.generate_user_config(
        tg_user=tg_user,
        ssh_client_factory=ssh_factory,
        server_info=server_info,
        node_name="ru",
    )

    assert file_path1.name == "test.conf"
    assert file_path2.name == "test.vpn"
    assert file_path3.name == "test.png"
    assert pub_key == "pubkey123"

    api_adapter.check_limit.assert_awaited_once_with(tg_id=123)

    user_adapter.register.assert_awaited_once()

    ssh_instance.add_new_user_gen_config.assert_awaited_once_with(file_name="test_user")

    api_adapter.add_config.assert_awaited_once_with(
        tg_id=123456,
        file_name="test.conf / test.vpn / test.png",
        pub_key="pubkey123",
        node_name="ru",
        backend="amnezia",
        protocol="wg_v2",
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
            node_name="ru",
        )

    err = exc.value

    assert err.tg_id == 123456
    assert err.limit == 1
    assert err.current == 1

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
        Path("/tmp/test.png"),
        "pubkey123",
    )

    ssh_factory = mocker.Mock()

    ssh_factory.return_value.__aenter__ = mocker.AsyncMock(return_value=ssh_instance)

    ssh_factory.return_value.__aexit__ = mocker.AsyncMock(return_value=None)

    api_adapter.add_config.side_effect = APIClientError(
        ErrorDetail(code="db_error", message="DB error")
    )

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
        protocol_version="v2",
    )

    with pytest.raises(APIClientError):
        await service.generate_user_config(
            tg_user=tg_user,
            ssh_client_factory=ssh_factory,
            server_info=server_info,
            node_name="ru",
        )

    ssh_instance.full_delete_user.assert_awaited_once_with(public_key="pubkey123")


@pytest.mark.asyncio
async def test_generate_user_config_rollback_uses_live_ssh_connection(mocker, user_out):
    """Регрессия на #267: откат обязан идти по ещё открытому SSH-соединению.

    `test_generate_user_config_db_error_rollback` выше не ловит этот баг,
    потому что там `ssh_instance` — чистый `AsyncMock`, который не меняет
    поведение после `__aexit__`. Двойник ниже имитирует реальный
    `AsyncContainerShellClient`: после выхода из `async with` любая команда,
    включая `full_delete_user`, обязана падать с `AmneziaSSHError`. Если
    сохранение в БД и откат выполняются уже после выхода из `async with`
    (старое поведение), `full_delete_user` обращается к закрытому клиенту —
    откат не происходит, а наверх уходит `AmneziaSSHError` вместо
    `APIClientError`.
    """

    class FakeSSHClient:
        def __init__(self) -> None:
            self.closed = False
            self.full_delete_user_called_with: str | None = None

        async def __aenter__(self) -> "FakeSSHClient":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            self.closed = True
            return False

        async def add_new_user_gen_config(
            self, file_name: str
        ) -> tuple[Path, Path, Path, str]:
            return (
                Path("/tmp/test.conf"),
                Path("/tmp/test.vpn"),
                Path("/tmp/test.png"),
                "pubkey123",
            )

        async def full_delete_user(self, public_key: str) -> None:
            if self.closed:
                raise AmneziaSSHError(
                    "AsyncSSH: shell-сессия не запущена. Вызови connect()"
                )
            self.full_delete_user_called_with = public_key

    ssh_instance = FakeSSHClient()
    ssh_factory = mocker.Mock(return_value=ssh_instance)

    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    tg_user = SimpleNamespace(id=123)

    api_adapter.check_limit.return_value = SVPNCheckLimitResponse(
        can_add=True,
        limit=5,
        current=1,
    )
    user_adapter.register.return_value = (user_out, True)
    api_adapter.add_config.side_effect = APIClientError(
        ErrorDetail(code="db_error", message="DB error")
    )

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
        protocol_version="v2",
    )

    with pytest.raises(APIClientError):
        await service.generate_user_config(
            tg_user=tg_user,
            ssh_client_factory=ssh_factory,
            server_info=server_info,
            node_name="ru",
        )

    assert ssh_instance.full_delete_user_called_with == "pubkey123"


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
        {
            "sub_ids": ["sub123"],
            "config_ids": ["cfg1", "cfg2"],
            "protocols": ["vless_reality_tcp", "vless_reality_xhttp"],
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
        node_name="ru",
        backend="xray",
        protocol="vless_reality_tcp,vless_reality_xhttp",
        config_ids=["cfg1", "cfg2"],
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

    api_adapter.add_config.side_effect = APIClientError(
        ErrorDetail(code="db_error", message="DB error")
    )

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
async def test_generate_xray_subscription_passes_exact_end_date(mocker):
    """Срок конфига на панели — это `end_date` подписки, а не целые дни от выдачи.

    Регрессия на #266: раньше срок пересчитывался в целые дни
    (`timedelta.days`), из-за чего короткие остатки подписки округлялись до
    нуля — а ноль 3x-ui трактует как "бессрочно".
    """
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
    assert args["expires_at"].replace(tzinfo=None) == future_date


@pytest.mark.asyncio
async def test_generate_xray_subscription_rejects_already_expired(mocker):
    """`end_date` в прошлом не должен давать бессрочный доступ.

    Регрессия на #266: `is_active` обновляется только планировщиком (#275),
    поэтому между истечением подписки и следующим прогоном планировщика флаг
    может ещё стоять `True`, хотя `end_date` уже в прошлом. Раньше такой
    остаток округлялся до `days_left=0`, то есть выдавался бессрочный
    конфиг — худший возможный исход именно для просроченной подписки.
    """
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    xray_registry.get.return_value = xray_adapter

    tg_user = SimpleNamespace(id=123)

    service = VPNService(api_adapter, user_adapter, xray_registry)

    past_date = datetime.now().replace(year=datetime.now().year - 1)

    user = mocker.Mock()
    user.telegram_id = 123
    user.current_subscription = SimpleNamespace(is_active=True, end_date=past_date)

    mocker.patch.object(
        service,
        "_limit_and_user_inf",
        return_value=user,
    )

    with pytest.raises(SubscriptionNotFoundError):
        await service.generate_xray_subscription(tg_user=tg_user, location="ru")

    xray_adapter.add_new_config.assert_not_called()


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

    config = SVPNConfigOut(
        id=1, file_name="conf1.conf", pub_key="PUBKEY", created_at=datetime(2026, 1, 1)
    )

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

    config = SVPNConfigOut(
        id=1,
        file_name="conf1.conf",
        pub_key='["cfg1"]',
        created_at=datetime(2026, 1, 1),
    )

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

    config = SVPNConfigOut(
        id=1, file_name="conf1.conf", pub_key="PUBKEY", created_at=datetime(2026, 1, 1)
    )

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

    config = SVPNConfigOut(
        id=1, file_name="conf1.conf", pub_key="PUBKEY", created_at=datetime(2026, 1, 1)
    )

    with pytest.raises(VPNConfigDeletionFailedError):
        await service.delete_user_config(tg_id=123, config=config)

    api_adapter.delete_config.assert_not_called()


@pytest.mark.asyncio
async def test_delete_user_config_known_xray_backend_skips_ssh(mocker):
    """`backend="xray"` известен заранее — SSH (Amnezia) вообще не пробуем."""
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    ssh_mock = mocker.patch.object(service, "_delete_from_ssh_nodes")
    mocker.patch.object(service, "_delete_from_xray", return_value=(True, False))

    config = SVPNConfigOut(
        id=1,
        file_name="loc_user_123",
        pub_key='["cfg1"]',
        backend="xray",
        node_name="sof",
        created_at=datetime(2026, 1, 1),
    )

    result = await service.delete_user_config(tg_id=123, config=config)

    assert result is True
    ssh_mock.assert_not_called()


@pytest.mark.asyncio
async def test_delete_user_config_known_amnezia_backend_skips_xray(mocker):
    """`backend="amnezia"` известен заранее — 3x-ui вообще не пробуем."""
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    mocker.patch.object(service, "_delete_from_ssh_nodes", return_value=(False, False))
    xray_mock = mocker.patch.object(service, "_delete_from_xray")

    config = SVPNConfigOut(
        id=1,
        file_name="conf1.conf",
        pub_key="PUBKEY",
        backend="amnezia",
        node_name="main",
        created_at=datetime(2026, 1, 1),
    )

    result = await service.delete_user_config(tg_id=123, config=config)

    assert result is False
    xray_mock.assert_not_called()


@pytest.mark.asyncio
async def test_delete_user_config_passes_node_name_through(mocker):
    """Известный node_name пробрасывается в оба хелпера удаления."""
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()

    service = VPNService(api_adapter, user_adapter, xray_registry)
    ssh_mock = mocker.patch.object(
        service, "_delete_from_ssh_nodes", return_value=(True, False)
    )
    mocker.patch.object(service, "_delete_from_xray")

    config = SVPNConfigOut(
        id=1,
        file_name="conf1.conf",
        pub_key="PUBKEY",
        node_name="sof",
        created_at=datetime(2026, 1, 1),
    )

    await service.delete_user_config(tg_id=123, config=config)

    ssh_mock.assert_awaited_once_with("PUBKEY", "conf1.conf", node_name="sof")


def test_group_xray_config_ids_backfilled_legacy_record():
    """Регрессия на #270: запись без `config_ids` после backfill — пропускается.

    Раньше для старых записей без `config_ids` бэкенд угадывался разбором
    `pub_key` как JSON. Миграция `1a242e081dff` заполнила `config_ids` для
    всех реальных XRay-записей, поэтому после неё запись без `config_ids`
    однозначно не XRay (WG-ключ в `pub_key`) — её нельзя спутать и не нужно
    разбирать. Этот тест проверяет оба случая одним списком конфигов: WG
    (без config_ids) пропускается, XRay (c config_ids) группируется.
    """
    configs = [
        SVPNConfigOut(
            id=1,
            file_name="wg.conf",
            pub_key="raw-wg-pubkey",
            backend="amnezia",
            created_at=datetime(2026, 1, 1),
        ),
        SVPNConfigOut(
            id=2,
            file_name="xray.conf",
            pub_key='["cfg1", "cfg2"]',
            backend="xray",
            node_name="sof",
            config_ids=["cfg1", "cfg2"],
            created_at=datetime(2026, 1, 1),
        ),
    ]

    by_node, legacy = VPNService._group_xray_config_ids(configs)

    assert by_node == {"sof": {"cfg1", "cfg2"}}
    assert legacy == set()


@pytest.mark.asyncio
async def test_delete_from_xray_no_config_ids_returns_not_found(mocker):
    """`config_ids=None` — не XRay-конфиг, ничего не удаляем и не ошибаемся.

    Регрессия на #270: раньше в этом случае код пытался разобрать `pub_key`
    как JSON. После backfill (миграция `1a242e081dff`) `config_ids=None`
    однозначно значит "не XRay" — разбирать нечего.
    """
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    service = VPNService(api_adapter, user_adapter, xray_registry)

    deleted, had_error = await service._delete_from_xray(
        "file.conf", node_name=None, config_ids=None
    )

    assert (deleted, had_error) == (False, False)
    xray_registry.all.assert_not_called()


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_no_active_subscription(mocker, user_out):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = user_out.model_copy(update={"current_subscription": None})

    result = await service.extend_user_xray_subscription(user=user)

    assert result == []
    xray_registry.all.assert_not_called()


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_no_xray_configs(mocker, user_out):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    xray_registry = mocker.Mock()
    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = user_out.model_copy(
        update={
            "current_subscription": SimpleNamespace(
                is_active=True, end_date=datetime(2999, 1, 1)
            ),
            "vpn_configs": [
                SVPNConfigOut(
                    id=1,
                    file_name="conf1.conf",
                    pub_key="raw-wg-pubkey",
                    created_at=datetime(2026, 1, 1),
                )
            ],
        }
    )

    result = await service.extend_user_xray_subscription(user=user)

    assert result == []
    xray_registry.all.assert_not_called()


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_success(mocker, user_out):
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_adapter.extend_config.return_value = ["cfg1", "cfg2"]
    xray_registry = mocker.Mock()
    xray_registry.all.return_value = [xray_adapter]

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = user_out.model_copy(
        update={
            "telegram_id": 123,
            "current_subscription": SimpleNamespace(
                is_active=True, end_date=datetime(2999, 1, 1)
            ),
            "vpn_configs": [
                SVPNConfigOut(
                    id=1,
                    file_name="loc_user_123",
                    pub_key='["cfg1", "cfg2"]',
                    backend="xray",
                    config_ids=["cfg1", "cfg2"],
                    created_at=datetime(2026, 1, 1),
                )
            ],
        }
    )

    result = await service.extend_user_xray_subscription(user=user)

    assert set(result) == {"cfg1", "cfg2"}
    xray_adapter.extend_config.assert_awaited_once()
    called_kwargs = xray_adapter.extend_config.await_args.kwargs
    assert set(called_kwargs["config_ids"]) == {"cfg1", "cfg2"}
    # #317: передаётся тот же абсолютный момент, что в подписке, без
    # округления до целых суток.
    assert called_kwargs["expires_at"].replace(tzinfo=None) == datetime(2999, 1, 1)


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_less_than_a_day_left_still_extends(
    mocker, user_out
):
    """#317: остаток меньше суток больше не схлопывается в "нечего продлевать".

    Раньше `days_left = (end - now).days` давало 0 при остатке 5 часов, и
    весь вызов пропускался — панель получала срок короче оплаченного на
    сутки. Теперь передаётся точный момент `end`, и продление происходит.
    """
    from bot.core.config import settings_bot

    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_adapter.extend_config.return_value = ["cfg1"]
    xray_registry = mocker.Mock()
    xray_registry.all.return_value = [xray_adapter]

    service = VPNService(api_adapter, user_adapter, xray_registry)

    end_date = datetime.now(settings_bot.core.tzinfo).replace(tzinfo=None) + timedelta(
        hours=5
    )
    user = user_out.model_copy(
        update={
            "telegram_id": 123,
            "current_subscription": SimpleNamespace(is_active=True, end_date=end_date),
            "vpn_configs": [
                SVPNConfigOut(
                    id=1,
                    file_name="loc_user_123",
                    pub_key='["cfg1"]',
                    backend="xray",
                    config_ids=["cfg1"],
                    created_at=datetime(2026, 1, 1),
                )
            ],
        }
    )

    result = await service.extend_user_xray_subscription(user=user)

    assert result == ["cfg1"]
    xray_adapter.extend_config.assert_awaited_once()
    called_kwargs = xray_adapter.extend_config.await_args.kwargs
    assert called_kwargs["expires_at"].replace(tzinfo=None) == end_date


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_unlimited_snaps_expiry(mocker, user_out):
    """#296: бессрочная подписка (end_date=None) снимает срок у конфигов
    через set_unlimited_config, а не пропускается как "нечего продлевать".
    """
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_adapter.set_unlimited_config.return_value = ["cfg1", "cfg2"]
    xray_registry = mocker.Mock()
    xray_registry.all.return_value = [xray_adapter]

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = user_out.model_copy(
        update={
            "telegram_id": 123,
            "current_subscription": SimpleNamespace(is_active=True, end_date=None),
            "vpn_configs": [
                SVPNConfigOut(
                    id=1,
                    file_name="loc_user_123",
                    pub_key='["cfg1", "cfg2"]',
                    backend="xray",
                    config_ids=["cfg1", "cfg2"],
                    created_at=datetime(2026, 1, 1),
                )
            ],
        }
    )

    result = await service.extend_user_xray_subscription(user=user)

    assert set(result) == {"cfg1", "cfg2"}
    xray_adapter.set_unlimited_config.assert_awaited_once()
    xray_adapter.extend_config.assert_not_called()
    called_kwargs = xray_adapter.set_unlimited_config.await_args.kwargs
    assert set(called_kwargs["config_ids"]) == {"cfg1", "cfg2"}


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_direct_node_lookup(mocker, user_out):
    """node_name известен — идём сразу на нужную ноду, без перебора всех."""
    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_adapter.extend_config.return_value = ["cfg1", "cfg2"]
    xray_registry = mocker.Mock()
    xray_registry.get_optional.return_value = xray_adapter

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = user_out.model_copy(
        update={
            "telegram_id": 123,
            "current_subscription": SimpleNamespace(
                is_active=True, end_date=datetime(2999, 1, 1)
            ),
            "vpn_configs": [
                SVPNConfigOut(
                    id=1,
                    file_name="loc_user_123",
                    pub_key='["cfg1", "cfg2"]',
                    backend="xray",
                    node_name="sof",
                    config_ids=["cfg1", "cfg2"],
                    created_at=datetime(2026, 1, 1),
                )
            ],
        }
    )

    result = await service.extend_user_xray_subscription(user=user)

    assert set(result) == {"cfg1", "cfg2"}
    xray_registry.get_optional.assert_called_once_with("sof")
    xray_registry.all.assert_not_called()


@pytest.mark.asyncio
async def test_extend_user_xray_subscription_not_found_anywhere_raises(
    mocker, user_out
):
    from bot.vpn.utils.x_ray_exceptions import ThreeXUIConfigNotFoundError

    api_adapter = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()

    xray_adapter = mocker.AsyncMock()
    xray_adapter.extend_config.side_effect = ThreeXUIConfigNotFoundError(
        config_ids=["cfg1"]
    )
    xray_registry = mocker.Mock()
    xray_registry.all.return_value = [xray_adapter]

    service = VPNService(api_adapter, user_adapter, xray_registry)

    user = user_out.model_copy(
        update={
            "current_subscription": SimpleNamespace(
                is_active=True, end_date=datetime(2999, 1, 1)
            ),
            "vpn_configs": [
                SVPNConfigOut(
                    id=1,
                    file_name="loc_user_123",
                    pub_key='["cfg1"]',
                    backend="xray",
                    config_ids=["cfg1"],
                    created_at=datetime(2026, 1, 1),
                )
            ],
        }
    )

    with pytest.raises(ThreeXUIConfigNotFoundError):
        await service.extend_user_xray_subscription(user=user)
