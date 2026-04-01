from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    # redis = mocker.AsyncMock()

    return VPNRouter(fake_bot, fake_logger, vpn_service, fake_redis)


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


@pytest.mark.asyncio
async def test_get_config_amnezia_vpn_success(mocker, router, message, user, state):
    router.redis.set.return_value = True

    # mock status message
    status_msg = mocker.MagicMock()
    status_msg.answer = mocker.AsyncMock()
    message.answer.return_value = status_msg

    # mock ssh client context manager
    ssh_client = mocker.AsyncMock()

    mocker.patch(
        "bot.vpn.router.AsyncSSHClientVPN",
        return_value=ssh_client,
    )

    ssh_client.__aenter__.return_value = ssh_client

    router.vpn_service.generate_user_config.return_value = (
        Path("/tmp/test.conf"),
        "pubkey",
    )

    mocker.patch("pathlib.Path.unlink")

    await router.get_config_amnezia_vpn(message=message, state=state)

    router.vpn_service.generate_user_config.assert_awaited_once()

    message.answer_document.assert_awaited_once()

    state.clear.assert_awaited_once()
    router.redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_config_amnezia_vpn_locked(router, message, user, state):
    router.redis.set.return_value = False

    await router.get_config_amnezia_vpn(message=message, state=state)

    router.vpn_service.generate_user_config.assert_not_called()
