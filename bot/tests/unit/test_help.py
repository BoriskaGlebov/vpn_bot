from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery

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
    ],
)
async def test_device_cb(
    make_fake_message,
    fake_bot,
    fake_logger,
    fake_state,
    monkeypatch,
    device_class,
    device_name,
):
    router = HelpRouter(bot=fake_bot, logger=fake_logger)
    fake_message = make_fake_message()
    # 👇 добавляем chat_instance (обязательный аргумент)
    fake_call = CallbackQuery(
        id="1",
        from_user=fake_message.from_user,
        message=fake_message,
        chat_instance="fake_chat_instance",
        data=f"device_{device_name}",
    ).as_(fake_bot)
    # Мокаем метод send_message устройства
    monkeypatch.setattr(device_class, "send_message", AsyncMock())

    await router.device_cb(fake_call, fake_state)

    device_class.send_message.assert_awaited_with(fake_bot, fake_message.chat.id)
    fake_state.clear.assert_awaited()


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

    # --- Создаем временную директорию с "медиа" ---
    media_dir = tmp_path / "bot" / "help" / "media" / media_folder
    media_dir.mkdir(parents=True)
    for i in range(3):
        (media_dir / f"{i}.png").touch()
    # --- Подготавливаем фейковые данные настроек ---
    fake_messages = [f"Шаг {i}" for i in range(3)]
    fake_settings = MagicMock()
    fake_settings.BASE_DIR = tmp_path
    fake_settings.MESSAGES = {
        "modes": {"help": {"instructions": {device_key: fake_messages}}}
    }

    # --- Подменяем настройки и sleep ---
    module_name = f"bot.help.utils.{device_key}_device"
    monkeypatch.setattr(f"{module_name}.settings_bot", fake_settings)
    monkeypatch.setattr(f"{module_name}.asyncio.sleep", AsyncMock())

    # --- Вызываем тестируемый метод ---
    await device_class.send_message(bot=fake_bot, chat_id=1234)
    # --- Проверяем, что send_photo вызван 3 раза ---
    assert fake_bot.send_photo.await_count == 3

    # --- Проверяем подписи в каждом вызове ---
    for i, call in enumerate(fake_bot.send_photo.await_args_list):
        kwargs = call.kwargs
        assert kwargs["chat_id"] == 1234
        assert kwargs["caption"] == f"Шаг {i}"
        assert str(kwargs["photo"].path).endswith(f"{i}.png")
