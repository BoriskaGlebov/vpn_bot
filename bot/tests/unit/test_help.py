from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery
from box import Box

from bot.help.keyboards.inline_kb import device_keyboard
from bot.help.router import HelpRouter, HelpStates, m_help
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.tv_device import TVDevice


@pytest.mark.asyncio
@pytest.mark.help
async def test_help_cmd(make_fake_message, fake_bot, fake_logger, fake_state):
    router = HelpRouter(bot=fake_bot, logger=fake_logger)
    fake_message = make_fake_message()

    await router.help_cmd(fake_message, fake_state)

    fake_state.clear.assert_awaited()
    calls = fake_message.answer.await_args_list
    first_call = calls[0].kwargs["text"]
    expected_text = m_help.get("welcome")
    assert first_call == expected_text
    fake_state.set_state.assert_awaited_with(HelpStates.device_state)
    actual_kb = calls[-1].kwargs["reply_markup"]
    expected_kb = device_keyboard()
    assert expected_kb == actual_kb


@pytest.mark.asyncio
@pytest.mark.help
@pytest.mark.parametrize(
    "device_class,device_name",
    [
        (AndroidDevice, "android"),
        (IphoneDevice, "ios"),
        (PCDevice, "pc"),
        (TVDevice, "tv"),
        (None, "device_developer"),
    ],
)
async def test_device_cb(
    make_fake_message,
    make_fake_query,
    fake_bot,
    fake_logger,
    fake_state,
    monkeypatch,
    device_class,
    device_name,
):
    router = HelpRouter(bot=fake_bot, logger=fake_logger)
    fake_message = make_fake_message()
    fake_call = make_fake_query(user_id=1, data=f"device_{device_name}")
    fake_call.message = fake_message
    fake_call.bot = fake_bot
    fake_call.bot.send_message = AsyncMock()
    fake_call.message.delete = AsyncMock()
    if device_name != "device_developer":
        monkeypatch.setattr(device_class, "send_message", AsyncMock())
    await router.device_cb(fake_call, fake_state)
    if device_name != "device_developer":
        device_class.send_message.assert_awaited_with(
            bot=fake_bot, chat_id=fake_message.chat.id
        )
        fake_state.clear.assert_awaited()
        fake_call.answer.assert_awaited_with(
            text=f"Ты выбрал {device_name}", show_alert=False
        )
    elif device_name == "device_developer":
        # Проверяем, что сообщение удаляется
        fake_message.delete.assert_awaited()
        # Проверяем, что отправляется сообщение с контактами
        fake_bot.send_message.assert_awaited_with(
            text="Для связи напишите @BorisisTheBlade",
            chat_id=fake_message.chat.id,
        )


@pytest.mark.asyncio
@pytest.mark.help
@pytest.mark.parametrize(
    "device_class, device_key, media_folder",
    [
        (AndroidDevice, "android", "amnezia_android"),
        (IphoneDevice, "iphone", "amnezia_iphone"),
        (PCDevice, "pc", "amnezia_pc"),
        (TVDevice, "tv", "amnezia_wg"),
    ],
)
async def test_device_send_message(
    fake_bot, monkeypatch, tmp_path, device_class, device_key, media_folder
):
    """Проверяет, что каждый класс устройства корректно отправляет фото с подписями."""

    # --- Подготавливаем фейковые данные настроек ---
    fake_messages = [f"Шаг {i}" for i in range(3)]
    fake_settings = MagicMock()
    fake_settings.base_dir = tmp_path
    fake_settings.messages = Box(
        {"modes": {"help": {"instructions": {device_key: fake_messages}}}},
        default_box=True,
    )

    # --- Подменяем настройки и sleep ---
    module_name = f"bot.help.utils.{device_key}_device"
    monkeypatch.setattr(f"{module_name}.settings_bot", fake_settings)
    monkeypatch.setattr(f"{module_name}.asyncio.sleep", AsyncMock())
    mocked_urls = [f"https://example.com/{media_folder}/{i}.png" for i in range(3)]
    monkeypatch.setattr(
        device_class, "_list_files", AsyncMock(return_value=mocked_urls)
    )

    # --- Вызываем тестируемый метод --
    await device_class.send_message(bot=fake_bot, chat_id=1234)
    # --- Проверяем, что send_photo вызван 3 раза ---
    assert fake_bot.send_photo.await_count == 3

    # --- Проверяем подписи в каждом вызове ---
    for i, call in enumerate(fake_bot.send_photo.await_args_list):
        kwargs = call.kwargs
        assert kwargs["chat_id"] == 1234
        assert kwargs["caption"] == f"Шаг {i}"
        photo_url = kwargs["photo"]
        assert isinstance(photo_url, str)
        assert photo_url.endswith(f"{i}.png")
