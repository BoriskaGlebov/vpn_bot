import asyncio
from typing import Any, Type
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from box import Box

from bot.help.keyboards.inline_kb import device_keyboard
from bot.help.router import HelpRouter, HelpStates, m_help
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.tv_device import TVDevice


@pytest.mark.asyncio
@pytest.mark.help
async def test_help_cmd(
    make_fake_message: Any,
    fake_bot: Any,
    fake_logger: Any,
    fake_state: Any,
    fake_redis: Any,
) -> None:
    """Проверяет команду /help.

    Сценарий:
        - пользователь вызывает команду help;
        - состояние очищается;
        - отправляется приветственное сообщение;
        - устанавливается новое состояние выбора устройства;
        - отправляется клавиатура с выбором устройств.

    Проверяется:
        - текст ответа;
        - установка состояния;
        - корректная клавиатура.
    """

    router = HelpRouter(bot=fake_bot, logger=fake_logger, redis=fake_redis)
    fake_message = make_fake_message()

    await router.help_cmd(fake_message, fake_state)

    fake_state.clear.assert_awaited()

    calls = fake_message.answer.await_args_list

    first_call_text: str = calls[0].kwargs["text"]
    expected_text: str = m_help.get("welcome")

    assert first_call_text == expected_text

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
    make_fake_message: Any,
    make_fake_query: Any,
    fake_bot: Any,
    fake_logger: Any,
    fake_state: Any,
    monkeypatch: pytest.MonkeyPatch,
    device_class: Type[Any] | None,
    device_name: str,
    fake_redis: Any,
) -> None:
    """Проверяет обработчик выбора устройства (callback).

    Сценарии:
        1. Пользователь выбирает устройство:
            - вызывается send_message соответствующего класса;
            - состояние очищается;
            - отправляется уведомление пользователю.
        2. Пользователь выбирает "developer":
            - сообщение удаляется;
            - отправляется сообщение с контактами.

    Проверяется:
        - корректный вызов send_message;
        - очистка состояния;
        - корректные ответы пользователю.
    """

    router = HelpRouter(bot=fake_bot, logger=fake_logger, redis=fake_redis)

    fake_message = make_fake_message()
    fake_call = make_fake_query(user_id=1, data=f"device_{device_name}")

    fake_call.message = fake_message
    fake_call.bot = fake_bot
    fake_call.bot.send_message = AsyncMock()
    fake_call.message.delete = AsyncMock()

    if device_name != "device_developer" and device_class is not None:
        # Подменяем send_message у конкретного девайса
        monkeypatch.setattr(device_class, "send_message", AsyncMock())

    await router.device_cb(fake_call, fake_state)

    if device_name != "device_developer" and device_class is not None:
        device_class.send_message.assert_awaited_with(
            bot=fake_bot,
            chat_id=fake_message.chat.id,
        )

        fake_state.clear.assert_awaited()

        fake_call.answer.assert_awaited_with(
            text=f"Ты выбрал {device_name}",
            show_alert=False,
        )

    else:
        # Проверяем ветку "developer"
        fake_message.delete.assert_awaited()

        fake_bot.send_message.assert_awaited_with(
            text="Для связи напишите @BorisisTheBlade",
            chat_id=fake_message.chat.id,
            reply_markup=ANY,
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
    fake_bot: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    device_class: Type[Any],
    device_key: str,
    media_folder: str,
) -> None:
    """Проверяет отправку инструкций для устройств.

    Сценарий:
        - для устройства загружаются инструкции (тексты + медиа);
        - для каждого шага отправляется сообщение с фото и подписью.

    Проверяется:
        - количество отправленных сообщений;
        - корректность chat_id;
        - соответствие caption тексту инструкции;
        - корректность URL изображения.
    """

    # --- Фейковые данные инструкций ---
    fake_messages: list[str] = [f"Шаг {i}" for i in range(3)]

    fake_settings = MagicMock()
    fake_settings.base_dir = tmp_path
    fake_settings.messages = Box(
        {"modes": {"help": {"instructions": {device_key: fake_messages}}}},
        default_box=True,
    )

    # --- Подмена зависимостей ---
    module_name = f"bot.help.utils.{device_key}_device"

    monkeypatch.setattr(f"{module_name}.settings_bot", fake_settings)

    # убираем реальные задержки
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    # подменяем источник текстов
    monkeypatch.setattr(device_class, "MESSAGES_PATH", fake_messages)

    # подменяем список файлов (медиа)
    mocked_urls: list[str] = [
        f"https://example.com/{media_folder}/{i}.png" for i in range(3)
    ]

    monkeypatch.setattr(
        device_class,
        "_list_files",
        AsyncMock(return_value=mocked_urls),
    )

    # --- Вызов ---
    await device_class.send_message(bot=fake_bot, chat_id=1234)

    # --- Проверки ---
    assert fake_bot.send_photo.await_count == 3

    for i, call in enumerate(fake_bot.send_photo.await_args_list):
        kwargs = call.kwargs

        assert kwargs["chat_id"] == 1234
        assert kwargs["caption"] == fake_messages[i]

        photo_url: str = kwargs["photo"]
        assert photo_url.endswith(f"{i}.png")
