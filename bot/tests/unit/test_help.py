import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.help.keyboards.inline_kb import device_keyboard
from bot.help.router import HelpStates, device_cb, help_cmd
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.tv_device import TVDevice


@pytest.mark.asyncio
async def test_help_cmd(monkeypatch, fake_bot, fake_state):
    """Проверяет, что help_cmd отправляет все сообщения и ставит состояния FSM."""

    # --- Arrange ---
    message = AsyncMock(spec=Message)
    message.chat = MagicMock()
    message.chat.id = 111
    message.answer = AsyncMock()
    # state = AsyncMock()
    m_help = {
        "start_block": [
            "Первое сообщение",
            "Второе сообщение",
            "Последнее сообщение",
        ]
    }

    # Подменяем зависимости внутри router.py
    monkeypatch.setattr("bot.help.router.m_help", m_help)
    monkeypatch.setattr("bot.help.router.bot", fake_bot)

    # ChatActionSender.typing — контекстный менеджер
    fake_ctx = AsyncMock()
    fake_ctx.__aenter__.return_value = None
    fake_ctx.__aexit__.return_value = None
    monkeypatch.setattr(
        "bot.help.router.ChatActionSender.typing", MagicMock(return_value=fake_ctx)
    )

    expected_keyboard = device_keyboard()
    assert isinstance(expected_keyboard, InlineKeyboardMarkup)
    # --- Act ---
    await help_cmd(message, fake_state)

    # --- Assert ---
    fake_state.set_state.assert_any_await(HelpStates.cmd_help)
    fake_state.set_state.assert_any_await(HelpStates.device_state)

    # Проверяем, что сообщение о старте отправлено
    message.answer.assert_any_await(
        "🚀 Супер, что выбрали этот пункт",
        reply_markup=ANY,
    )

    # Проверяем, что последнее сообщение имеет клавиатуру
    message.answer.assert_any_await(
        "Последнее сообщение",
        reply_markup=expected_keyboard,
    )
    # Дополнительно — проверим состав кнопок клавиатуры
    buttons = [btn for row in expected_keyboard.inline_keyboard for btn in row]
    texts = [b.text for b in buttons]
    callbacks = [b.callback_data for b in buttons]

    assert texts == ["📱 Android", "🍏 iOS", "💻 Windows / Linux", "📺 Smart TV"]
    assert callbacks == ["device_android", "device_ios", "device_pc", "device_tv"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_name,device_class",
    [
        ("android", "AndroidDevice"),
        ("ios", "IphoneDevice"),
        ("pc", "PCDevice"),
        ("tv", "TVDevice"),
    ],
)
async def test_device_cb(monkeypatch, fake_bot, device_name, device_class, fake_state):
    """Проверяет, что при выборе устройства вызывается нужный метод .send_message()."""

    call = AsyncMock(spec=CallbackQuery)
    call.message = MagicMock()
    call.data = f"device_{device_name}"
    call.message.chat.id = 999
    call.answer = AsyncMock()

    # state = AsyncMock()

    fake_ctx = AsyncMock()
    fake_ctx.__aenter__.return_value = None
    fake_ctx.__aexit__.return_value = None
    monkeypatch.setattr(
        "bot.help.router.ChatActionSender.typing", MagicMock(return_value=fake_ctx)
    )
    monkeypatch.setattr("bot.help.router.bot", fake_bot)

    fake_device_cls = AsyncMock()
    monkeypatch.setattr(f"bot.help.router.{device_class}", fake_device_cls)

    await device_cb(call, fake_state)

    call.answer.assert_awaited_once_with(
        text=f"Ты выбрал {device_name}", show_alert=False
    )
    fake_device_cls.send_message.assert_awaited_once_with(
        fake_bot, call.message.chat.id
    )
    fake_state.clear.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class, media_dir, msg_key",
    [
        (AndroidDevice, "amnezia_android", "android"),
        (IphoneDevice, "amnezia_iphone", "iphone"),
        (PCDevice, "amnezia_pc", "pc"),
        (TVDevice, "amnezia_wg", "tv"),
    ],
)
async def test_device_send_message(
    monkeypatch, fake_bot, tmp_path, device_class, media_dir, msg_key
):
    """Проверяет, что все классы устройств корректно отправляют сообщения."""

    # --- Arrange ---
    # Создаём временную директорию с файлами
    media_dir_path = tmp_path / "bot" / "help" / "media" / media_dir
    media_dir_path.mkdir(parents=True)
    (media_dir_path / "1.png").write_text("fake image")
    (media_dir_path / "2.png").write_text("fake image")

    messages = {
        "modes": {
            "help": {
                "instructions": {
                    msg_key: ["Шаг 1", "Шаг 2"],
                }
            }
        }
    }

    # Мокаем настройки и утилиты
    monkeypatch.setattr("bot.config.settings_bot.BASE_DIR", tmp_path)
    monkeypatch.setattr("bot.config.settings_bot.MESSAGES", messages)
    monkeypatch.setattr(
        f"bot.help.utils.{msg_key}_device.settings_bot",
        MagicMock(BASE_DIR=tmp_path, MESSAGES=messages),
    )

    fake_file = MagicMock()
    monkeypatch.setattr("aiogram.types.FSInputFile", MagicMock(return_value=fake_file))
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    chat_id = 777
    fake_bot.send_photo = AsyncMock()

    # --- Act ---
    await device_class.send_message(fake_bot, chat_id)

    # --- Assert ---
    # Проверяем, что send_photo вызывался столько же раз, сколько файлов
    assert fake_bot.send_photo.await_count == 2

    # Проверяем, что передаются правильные подписи
    calls = fake_bot.send_photo.await_args_list
    captions = [c.kwargs["caption"] for c in calls]
    assert captions == ["Шаг 1", "Шаг 2"]

    # Проверяем, что используется корректный chat_id
    for c in calls:
        assert c.kwargs["chat_id"] == chat_id

    # Проверяем, что sleep был вызван после каждой отправки
    asyncio.sleep.assert_awaited()


@pytest.mark.asyncio
async def test_device_send_message_raises_file_not_found(tmp_path):
    # создаём мок настроек
    settings_mock = SimpleNamespace(
        BASE_DIR=tmp_path,
        MESSAGES={"modes": {"help": {"instructions": {"android": ["тест"]}}}},
    )

    fake_bot = AsyncMock()

    # Патчим settings_bot там, где он реально используется
    with patch("bot.help.utils.android_device.settings_bot", settings_mock):
        # Импортируем AndroidDevice после патча
        from bot.help.utils.android_device import AndroidDevice

        expected_dir = tmp_path / "bot" / "help" / "media" / "amnezia_android"
        assert not expected_dir.exists()  # убедимся, что папки нет

        # Проверяем, что поднимается FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            await AndroidDevice.send_message(fake_bot, 999)

        # Проверяем, что путь указан в ошибке
        assert str(expected_dir) in str(exc_info.value)
