from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.subscription.router import SubscriptionStates
from bot.vpn.router import VPNRouter


@pytest.fixture
def message(make_fake_message):
    msg = make_fake_message()

    # msg.chat.id = 123
    # msg.answer = mocker.AsyncMock()
    # msg.answer_document = mocker.AsyncMock()

    return msg


@pytest.fixture
def state(fake_state):
    # state = mocker.MagicMock()
    # state.clear = mocker.AsyncMock()
    state = fake_state
    return state


@pytest.fixture
def user(tg_user):
    return tg_user


@pytest.fixture
def router(fake_bot, fake_logger, mocker, fake_redis):
    # bot = mocker.AsyncMock()
    # logger = mocker.MagicMock()
    vpn_service = mocker.AsyncMock()
    subscription_service = mocker.AsyncMock()
    user_adapter = mocker.AsyncMock()
    # redis = mocker.AsyncMock()

    return VPNRouter(
        fake_bot,
        fake_logger,
        vpn_service,
        fake_redis,
        subscription_service,
        user_adapter,
    )


@pytest.mark.asyncio
async def test_check_acquired_success(router, message):
    router.redis.set.return_value = True

    result = await router._check_acquired("key", message)

    assert result is True
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_check_acquired_already_running(router, message):
    router.redis.set.return_value = False

    result = await router._check_acquired("key", message)

    assert result is False
    message.answer.assert_awaited_once()


# @pytest.mark.asyncio
# async def test_get_config_amnezia_vpn_success(mocker, router, message, user, state):
#     router.redis.set.return_value = True
#
#     # FIX: обходим логику определения локации
#     mocker.patch.object(
#         router,
#         "_get_location_server",
#         return_value="fi",
#     )
#
#     server_info = mocker.Mock()
#     router._get_location_server.return_value = "fi"
#     router.vpn_service.generate_user_config.return_value = (
#         Path("/tmp/test.conf"),
#         "pubkey",
#     )
#
#     # mock FSM message answer
#     status_msg = mocker.MagicMock()
#     status_msg.answer = mocker.AsyncMock()
#     message.answer.return_value = status_msg
#
#     mocker.patch("pathlib.Path.unlink")
#
#     await router.get_config_amnezia_vpn(
#         message=message,
#         state=state,
#     )
#
#     router.vpn_service.generate_user_config.assert_awaited_once()
#     message.answer_document.assert_awaited_once()
#     state.clear.assert_awaited_once()
#     router.redis.delete.assert_awaited_once()

#
# @pytest.mark.asyncio
# async def test_get_config_amnezia_vpn_locked(
#     mocker,
#     router,
#     message,
#     state,
# ):
#     router.redis.set.return_value = False
#
#     # чтобы роутер не упал на определении локации
#     mocker.patch.object(
#         router,
#         "_get_location_server",
#         return_value="fi",
#     )
#
#     await router.get_config_amnezia_vpn(
#         message=message,
#         state=state,
#     )
#
#     router.vpn_service.generate_user_config.assert_not_called()
#
#     message.answer.assert_awaited_once_with(
#         "⏳ Генерация вашего конфига уже в процессе, подождите немного."
#     )


@pytest.mark.asyncio
async def test_get_config_amnezia_wg_success(
    mocker,
    router,
    message,
    state,
):
    router.redis.set.return_value = True

    # чтобы не падало на определении локации
    mocker.patch.object(
        router,
        "_get_location_server",
        return_value="fi",
    )

    status_msg = mocker.MagicMock()
    status_msg.answer = mocker.AsyncMock()

    message.answer.return_value = status_msg
    message.answer_media_group = mocker.AsyncMock()

    router.vpn_service.generate_user_config.return_value = (
        Path("/tmp/test_wg.conf"),
        Path("/tmp/test_wg.vpn"),
        "pubkey",
    )

    mocker.patch("pathlib.Path.unlink")

    await router.get_config_amnezia_wg(
        message=message,
        state=state,
    )

    router.vpn_service.generate_user_config.assert_awaited_once()

    message.answer_media_group.assert_awaited_once()

    state.clear.assert_awaited_once()

    router.redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_proxy_url_no_subscription(mocker, router, message, user, state):
    router.redis.set.return_value = True

    status_msg = mocker.MagicMock()
    status_msg.answer = mocker.AsyncMock()
    message.answer.return_value = status_msg

    router.subscription_service.get_subscription_info = mocker.AsyncMock(
        return_value="Не активна"
    )

    client = mocker.AsyncMock()
    mocker.patch(
        "bot.vpn.router.HostDockerSSHClient",
        return_value=client,
    )
    client.__aenter__.return_value = client

    with pytest.raises(Exception):
        await router.create_proxy_url(message=message, state=state)


@pytest.mark.asyncio
async def test_create_proxy_url_success(
    mocker,
    router,
    message,
    state,
):
    router.redis.set.return_value = True

    router.subscription_service.get_subscription_info = mocker.AsyncMock(
        return_value="Активна",
    )

    router.vpn_service.get_mtproto_url = mocker.AsyncMock(
        return_value="tg://proxy",
    )

    message.answer = mocker.AsyncMock()

    await router.create_proxy_url(
        message=message,
        state=state,
    )

    router.vpn_service.get_mtproto_url.assert_awaited_once()

    message.answer.assert_awaited()

    state.clear.assert_awaited_once()

    router.redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_free_proxy_url_success(
    mocker,
    router,
    message,
    state,
):
    router.redis.set.return_value = True

    router.vpn_service.get_mtproto_url = mocker.AsyncMock(
        return_value="tg://proxy",
    )

    message.answer = mocker.AsyncMock()

    await router.create_free_proxy_url(
        message=message,
        state=state,
    )

    router.vpn_service.get_mtproto_url.assert_awaited_once()

    message.answer.assert_awaited()

    state.clear.assert_awaited_once()

    router.redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_three_x_ui_locations_sets_state(mocker, router, message, user, state):
    message.answer = mocker.AsyncMock()

    await router.three_x_ui_locations(message=message, state=state)

    message.answer.assert_awaited_once()
    state.set_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_subscription_success(
    mocker,
    router,
    message,
    state,
):
    message.answer = mocker.AsyncMock()

    mocker.patch.object(
        router,
        "_get_location_server",
        return_value="fi",
    )

    router.vpn_service.generate_xray_subscription = mocker.AsyncMock(
        return_value="https://subscription.url",
    )

    await router.generate_subscription(
        message=message,
        state=state,
    )

    state.clear.assert_awaited_once()

    router.vpn_service.generate_xray_subscription.assert_awaited_once()

    kwargs = router.vpn_service.generate_xray_subscription.await_args.kwargs

    assert kwargs["location"] == "fi"
    assert kwargs["tg_user"].id == 123

    assert message.answer.await_count == 2


@pytest.mark.asyncio
async def test_upgrade_subscription_success(
    mocker,
    router,
    message,
    state,
):
    message.answer = mocker.AsyncMock()

    await router.upgrade_subscription(
        message=message,
        state=state,
    )

    state.set_state.assert_awaited_once_with(
        SubscriptionStates.subscription_start,
    )

    state.update_data.assert_awaited_once_with(
        premium=True,
    )

    message.answer.assert_awaited_once()

    kwargs = message.answer.await_args.kwargs

    assert "text" in kwargs
    assert kwargs["text"]

    assert kwargs["reply_markup"] is not None
