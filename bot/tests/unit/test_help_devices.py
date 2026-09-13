import asyncio
import base64
import binascii
import json
import re
import string
from typing import Any, Type
from unittest.mock import ANY, AsyncMock

import pytest

from bot.app_error.base_error import (
    DeviceEmptyMediaError,
    DeviceEmptyMessagesError,
    DeviceInstructionMismatchError,
    DeviceMediaMismatchError,
)
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.common_device import Device
from bot.help.utils.incy_device import IncyDevice
from bot.help.utils.routing_device import RoutingHappDevice, RoutingIncyDevice


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Убирает паузы между отправкой фото во всех тестах модуля."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


def _fake_media(count: int) -> list[str]:
    """Возвращает список ссылок-заглушек на файлы из S3."""
    return [f"https://example.com/{i}.png" for i in range(count)]


def _patch_device(
    monkeypatch: pytest.MonkeyPatch,
    device: Type[Device],
    *,
    messages: list[str],
    media: list[str],
    link: Any = None,
) -> None:
    """Подменяет источники данных устройства на тестовые.

    Args:
        monkeypatch (pytest.MonkeyPatch): Фикстура подмены атрибутов.
        device (Type[Device]): Класс устройства.
        messages (list[str]): Подписи из конфигурации.
        media (list[str]): Ссылки на файлы из S3.
        link (Any): Значение `LINK_PATH` (строка, список или словарь).

    """
    monkeypatch.setattr(device, "MESSAGES_PATH", messages)
    monkeypatch.setattr(device, "LINK_PATH", link)
    monkeypatch.setattr(device, "_list_files", AsyncMock(return_value=media))


def _placeholders(text: str) -> set[str]:
    """Возвращает имена именованных `{}`-плейсхолдеров в строке."""
    return {
        name for _, name, _, _ in string.Formatter().parse(text) if name is not None
    }


class _PlainDevice(Device):
    """Устройство-пустышка для проверки логики базового класса."""

    PREFIX = "test/"
    MESSAGES_PATH: list[str] = []
    LINK_PATH: str | None = None


@pytest.mark.asyncio
@pytest.mark.help
async def test_send_intro_media_final_with_final(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверяет формат «вступление + подписи + финал».

    Сценарий:
        - подписей на две больше, чем файлов.

    Проверяется:
        - вступление и финал уходят отдельными сообщениями;
        - подписи привязаны к файлам один к одному и в том же порядке;
        - предпросмотр ссылок отключён.
    """
    messages = ["интро", "шаг 1", "шаг 2", "финал"]
    media = _fake_media(2)
    _patch_device(monkeypatch, _PlainDevice, messages=messages, media=media)

    await _PlainDevice._send_intro_media_final(
        fake_bot, 42, intro_formatter=lambda text: text
    )

    assert fake_bot.send_message.await_count == 2
    first, last = fake_bot.send_message.await_args_list
    assert first.args == (42, "интро")
    assert first.kwargs["disable_web_page_preview"] is True
    assert last.args == (42, "финал")

    assert fake_bot.send_photo.await_count == 2
    for i, call in enumerate(fake_bot.send_photo.await_args_list):
        assert call.kwargs["chat_id"] == 42
        assert call.kwargs["photo"] == media[i]
        assert call.kwargs["caption"] == messages[i + 1]
        assert call.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
@pytest.mark.help
async def test_send_intro_media_final_without_final(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверяет формат без финального сообщения.

    Сценарий:
        - подписей ровно на одну больше, чем файлов.

    Проверяется:
        - отправляется только вступление;
        - последняя подпись уходит как caption, а не отдельным сообщением.
    """
    messages = ["интро", "шаг 1", "шаг 2"]
    _patch_device(monkeypatch, _PlainDevice, messages=messages, media=_fake_media(2))

    await _PlainDevice._send_intro_media_final(
        fake_bot, 42, intro_formatter=lambda text: text
    )

    fake_bot.send_message.assert_awaited_once()
    assert fake_bot.send_photo.await_count == 2
    assert fake_bot.send_photo.await_args_list[-1].kwargs["caption"] == "шаг 2"


@pytest.mark.asyncio
@pytest.mark.help
async def test_final_formatter_defaults_to_intro(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверяет, что финал форматируется так же, как вступление.

    Это поведение по умолчанию используют INCY и профили маршрутизации:
    они не передают `final_formatter`, рассчитывая, что ссылки подставятся
    в финальное сообщение теми же правилами, что и во вступление.

    Проверяется:
        - без явного `final_formatter` к финалу применяется `intro_formatter`;
        - явный `final_formatter` имеет приоритет;
        - `caption_formatter` по умолчанию оставляет подписи как есть.
    """
    messages = ["{link}", "подпись {link}", "{link}"]
    _patch_device(monkeypatch, _PlainDevice, messages=messages, media=_fake_media(1))

    await _PlainDevice._send_intro_media_final(
        fake_bot, 42, intro_formatter=lambda text: text.format(link="ИНТРО")
    )
    intro, final = fake_bot.send_message.await_args_list
    assert intro.args[1] == "ИНТРО"
    assert final.args[1] == "ИНТРО"
    # По умолчанию подпись не форматируется — плейсхолдер остаётся сырым.
    assert fake_bot.send_photo.await_args.kwargs["caption"] == "подпись {link}"

    fake_bot.send_message.reset_mock()
    await _PlainDevice._send_intro_media_final(
        fake_bot,
        42,
        intro_formatter=lambda text: text.format(link="ИНТРО"),
        caption_formatter=lambda text: text.format(link="ПОДПИСЬ"),
        final_formatter=lambda text: text.format(link="ФИНАЛ"),
    )
    assert fake_bot.send_message.await_args_list[-1].args[1] == "ФИНАЛ"
    assert fake_bot.send_photo.await_args.kwargs["caption"] == "подпись ПОДПИСЬ"


@pytest.mark.asyncio
@pytest.mark.help
@pytest.mark.parametrize(
    "messages, media_count, expected_error",
    [
        ([], 2, DeviceEmptyMessagesError),
        (["интро", "шаг"], 0, DeviceEmptyMediaError),
        (["интро"], 2, DeviceInstructionMismatchError),
        (["интро", "1", "2", "3", "финал"], 2, DeviceInstructionMismatchError),
    ],
    ids=["нет подписей", "нет файлов", "подписей меньше", "подписей больше"],
)
async def test_send_intro_media_final_validation(
    fake_bot: Any,
    monkeypatch: pytest.MonkeyPatch,
    messages: list[str],
    media_count: int,
    expected_error: Type[Exception],
) -> None:
    """Проверяет валидацию количества подписей и файлов.

    Рассинхрон между YAML и S3 должен падать сразу и с понятной ошибкой,
    а не отправлять пользователю обрезанную инструкцию.

    Проверяется:
        - для каждого вида рассинхрона поднимается своя ошибка;
        - пользователю при этом ничего не отправляется.
    """
    _patch_device(
        monkeypatch, _PlainDevice, messages=messages, media=_fake_media(media_count)
    )

    with pytest.raises(expected_error):
        await _PlainDevice._send_intro_media_final(
            fake_bot, 42, intro_formatter=lambda text: text
        )

    fake_bot.send_message.assert_not_awaited()
    fake_bot.send_photo.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.help
async def test_send_message_media_mismatch(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверяет валидацию в базовом `send_message`.

    Проверяется:
        - при разном количестве файлов и подписей поднимается
          `DeviceMediaMismatchError`.
    """
    _patch_device(
        monkeypatch, _PlainDevice, messages=["один"], media=_fake_media(3), link="url"
    )

    with pytest.raises(DeviceMediaMismatchError):
        await _PlainDevice.send_message(bot=fake_bot, chat_id=42)


@pytest.mark.asyncio
@pytest.mark.help
@pytest.mark.parametrize("link", ["https://example.com/app", None], ids=["есть", "нет"])
async def test_send_download_block_default(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch, link: str | None
) -> None:
    """Проверяет базовый хук отправки блока со ссылкой на приложение.

    Проверяется:
        - при заданной ссылке уходит кнопка со ссылкой на установку;
        - при пустой ссылке блок не отправляется вовсе.
    """
    send_link_button = AsyncMock()
    monkeypatch.setattr(
        "bot.help.utils.common_device.send_link_button", send_link_button
    )
    _patch_device(
        monkeypatch, _PlainDevice, messages=["шаг"], media=_fake_media(1), link=link
    )

    await _PlainDevice.send_message(bot=fake_bot, chat_id=42)

    if link:
        send_link_button.assert_awaited_once_with(
            fake_bot, 42, text="Скачайте приложение по ссылке:", url=link
        )
    else:
        send_link_button.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.help
async def test_android_send_download_block_overrides_base(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверяет, что Android подменяет финальный блок выбором способа установки.

    Вместо одной кнопки «Скачать» Android показывает Google Play и переход
    к прямым APK-ссылкам — для тех, у кого Google Play недоступен.

    Проверяется:
        - базовая кнопка-ссылка не отправляется;
        - уходит сообщение с текстом из конфигурации и клавиатурой,
          где есть кнопка на Google Play и кнопка выбора APK.
    """
    send_link_button = AsyncMock()
    monkeypatch.setattr(
        "bot.help.utils.common_device.send_link_button", send_link_button
    )
    play_url = "https://play.google.com/store/apps/details?id=org.amnezia.vpn"
    _patch_device(
        monkeypatch,
        AndroidDevice,
        messages=["шаг"],
        media=_fake_media(1),
        link=play_url,
    )

    await AndroidDevice.send_message(bot=fake_bot, chat_id=42)

    send_link_button.assert_not_awaited()
    fake_bot.send_message.assert_awaited_once_with(
        chat_id=42, text=AndroidDevice.APK_PATH.choose, reply_markup=ANY
    )

    buttons = [
        button
        for row in fake_bot.send_message.await_args.kwargs[
            "reply_markup"
        ].inline_keyboard
        for button in row
    ]
    assert [button.url for button in buttons] == [play_url, None]
    assert buttons[-1].callback_data.startswith("apk:")


@pytest.mark.asyncio
@pytest.mark.help
async def test_incy_formats_named_links(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проверяет подстановку именованных ссылок в инструкцию INCY.

    У INCY, в отличие от Happ, ссылки заданы словарём — порядок строк
    в тексте можно менять, не ломая ссылки.

    Проверяется:
        - ссылки подставляются и во вступление, и в финал;
        - в подписи к фото подстановка не выполняется.
    """
    links = {
        "android": "https://play.example/incy",
        "ios": "https://apps.example/incy",
        "windows": "https://example.com/incy.zip",
        "linux": "https://example.com/releases",
    }
    messages = ['<a href="{android}">A</a>', "шаг", '<a href="{linux}">L</a>']
    _patch_device(
        monkeypatch, IncyDevice, messages=messages, media=_fake_media(1), link=links
    )

    await IncyDevice.send_message(bot=fake_bot, chat_id=42)

    intro, final = fake_bot.send_message.await_args_list
    assert intro.args[1] == f'<a href="{links["android"]}">A</a>'
    assert final.args[1] == f'<a href="{links["linux"]}">L</a>'
    assert fake_bot.send_photo.await_args.kwargs["caption"] == "шаг"


@pytest.mark.asyncio
@pytest.mark.help
@pytest.mark.parametrize(
    "device", [RoutingHappDevice, RoutingIncyDevice], ids=["happ", "incy"]
)
async def test_routing_formats_link(
    fake_bot: Any, monkeypatch: pytest.MonkeyPatch, device: Type[Device]
) -> None:
    """Проверяет подстановку deeplink-а профиля маршрутизации.

    Проверяется:
        - `{link}` заменяется и во вступлении, и в финале;
        - подписи к фото остаются без изменений.
    """
    deeplink = "scheme://routing/add/payload"
    messages = ["интро {link}", "шаг", "финал <code>{link}</code>"]
    _patch_device(
        monkeypatch, device, messages=messages, media=_fake_media(1), link=deeplink
    )

    await device.send_message(bot=fake_bot, chat_id=42)

    intro, final = fake_bot.send_message.await_args_list
    assert intro.args[1] == f"интро {deeplink}"
    assert final.args[1] == f"финал <code>{deeplink}</code>"
    assert fake_bot.send_photo.await_args.kwargs["caption"] == "шаг"


@pytest.mark.help
@pytest.mark.parametrize(
    "device, scheme",
    [(RoutingHappDevice, "happ"), (RoutingIncyDevice, "incy")],
    ids=["happ", "incy"],
)
def test_routing_deeplink_is_valid(device: Type[Device], scheme: str) -> None:
    """Проверяет целостность deeplink-а профиля в конфигурации.

    Профили лежат в YAML одной строкой в две тысячи символов, поэтому
    при правке их легко обрезать. Ошибку нужно ловить тестом, а не
    жалобой пользователя, у которого не импортировался профиль.

    Проверяется:
        - схема ссылки соответствует клиенту;
        - base64-полезная нагрузка декодируется в валидный JSON;
        - профиль описывает разделение трафика (российские сайты — напрямую).
    """
    link = device.LINK_PATH
    assert isinstance(link, str)
    prefix = f"{scheme}://routing/add/"
    assert link.startswith(prefix), f"ожидалась схема {prefix}"

    payload = link.removeprefix(prefix)
    try:
        # Профиль INCY приходит без выравнивающих «=» — добавляем сами.
        raw = base64.b64decode(payload + "=" * ((-len(payload)) % 4))
    except binascii.Error as exc:  # pragma: no cover - защита от битой строки
        pytest.fail(f"{device.__name__}: base64 не декодируется ({exc})")

    profile = json.loads(raw)
    assert profile["Name"]
    assert "geosite:category-ru" in profile["DirectSites"]


@pytest.mark.help
@pytest.mark.parametrize(
    "device, expected",
    [
        (RoutingHappDevice, {"link"}),
        (RoutingIncyDevice, {"link"}),
        (IncyDevice, {"android", "ios", "windows", "linux"}),
    ],
    ids=["routing_happ", "routing_incy", "incy"],
)
def test_config_placeholders_are_resolvable(
    device: Type[Device], expected: set[str]
) -> None:
    """Проверяет, что все плейсхолдеры в текстах закрыты ссылками.

    Опечатка в имени плейсхолдера превращается в `KeyError` уже во время
    отправки — пользователь получает часть инструкции и общую ошибку.

    Проверяется:
        - в текстах не встречается имён, которых нет в `LINK_PATH`;
        - `<code>`-блоки с deeplink-ом не содержат ничего, кроме плейсхолдера.
    """
    for message in device.MESSAGES_PATH:
        assert _placeholders(message) <= expected, f"неизвестный плейсхолдер: {message}"

    if expected == {"link"}:
        codes = re.findall(r"<code>(.*?)</code>", "\n".join(device.MESSAGES_PATH))
        assert codes, "в инструкции нет <code>-блока со ссылкой на профиль"
        assert set(codes) == {"{link}"}, "в <code> должен быть только deeplink"


@pytest.mark.help
def test_routing_devices_use_separate_sources() -> None:
    """Проверяет, что Happ и INCY не делят между собой данные.

    Классы отличаются только константами, поэтому копипаста при добавлении
    третьего клиента — реальный риск: инструкция INCY со ссылкой Happ
    выглядит рабочей, но профиль не импортируется.

    Проверяется:
        - префикс в S3, тексты и ссылка у клиентов разные.
    """
    assert RoutingHappDevice.PREFIX != RoutingIncyDevice.PREFIX
    assert RoutingHappDevice.LINK_PATH != RoutingIncyDevice.LINK_PATH
    assert RoutingHappDevice.MESSAGES_PATH != RoutingIncyDevice.MESSAGES_PATH
