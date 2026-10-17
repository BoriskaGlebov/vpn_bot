from pathlib import Path

import pytest

from bot.subscription.router import SubscriptionStates
from bot.users.enums import Location, VPNProtocol
from bot.users.utils.text_generator import vpn_button_text
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


@pytest.mark.asyncio
async def test_get_config_amnezia_wg_success(
    mocker,
    router,
    message,
    state,
):
    router.redis.set.return_value = True

    status_msg = mocker.MagicMock()
    status_msg.edit_text = mocker.AsyncMock()

    message.answer.return_value = status_msg
    message.answer_media_group = mocker.AsyncMock()
    message.answer_photo = mocker.AsyncMock()

    router.vpn_service.generate_user_config.return_value = (
        Path("/tmp/test_wg.conf"),
        Path("/tmp/test_wg.vpn"),
        Path("/tmp/test_wg.png"),
        "pubkey",
    )

    mocker.patch("pathlib.Path.unlink")

    await router.get_config_amnezia_wg(
        message=message,
        state=state,
        location=Location.MAIN,
    )

    router.vpn_service.generate_user_config.assert_awaited_once()

    message.answer_media_group.assert_awaited_once()
    message.answer_photo.assert_awaited_once()

    state.clear.assert_awaited_once()

    router.redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_location_flag_reaches_handler_via_real_dispatch(
    mocker, router, make_fake_message, state
):
    """Регрессия на #268: локация доходит до хендлера через flags, не через текст.

    Раньше локация выводилась повторным разбором текста кнопки
    (`_get_location_server`) — подстрочным совпадением, срабатывавшим
    "случайно" (например, `'sof' in 'Sofia'`). Здесь сообщение с текстом
    кнопки MAIN прогоняется через настоящий `router.router.message.trigger`
    (не через прямой вызов хендлера) — так проверяется именно связка
    `flags={"location": ...}` + `LocationFlagMiddleware`, а не её отдельные
    части.
    """
    message = make_fake_message(
        text=vpn_button_text(VPNProtocol.AMNEZIA, Location.MAIN)
    )

    status_msg = mocker.MagicMock()
    status_msg.edit_text = mocker.AsyncMock()
    message.answer.return_value = status_msg
    message.answer_media_group = mocker.AsyncMock()
    message.answer_photo = mocker.AsyncMock()

    router.redis.set.return_value = True
    router.vpn_service.generate_user_config.return_value = (
        Path("/tmp/test_wg.conf"),
        Path("/tmp/test_wg.vpn"),
        Path("/tmp/test_wg.png"),
        "pubkey",
    )
    mocker.patch("pathlib.Path.unlink")

    await router.router.message.trigger(message, state=state)

    router.vpn_service.generate_user_config.assert_awaited_once()
    kwargs = router.vpn_service.generate_user_config.await_args.kwargs
    assert kwargs["node_name"] == "main"


@pytest.mark.asyncio
async def test_three_x_ui_locations_sends_locations(mocker, router, message):
    message.answer = mocker.AsyncMock()

    await router.three_x_ui_locations(message=message)

    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_subscription_success(
    mocker,
    router,
    message,
    state,
):
    message.answer = mocker.AsyncMock()

    router.vpn_service.generate_xray_subscription = mocker.AsyncMock(
        return_value="https://subscription.url",
    )

    await router.generate_subscription(
        message=message,
        state=state,
        location=Location.FINLAND,
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
