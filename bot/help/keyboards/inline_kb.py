from collections.abc import Mapping
from enum import StrEnum

from aiogram import Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ApkAction(StrEnum):
    """Экраны пошагового выбора APK-файла AmneziaVPN для Android.

    Значение — это экран, который нужно показать по нажатию кнопки.
    Все три экрана живут в одном сообщении (`edit_text`), поэтому
    кнопки "Назад" — это просто переход на предыдущий экран.

    Attributes
        CHOICE: Выбор способа установки — Google Play или прямой APK.
        VERSIONS: Выбор версии Android.
        FILES: Выбор файла под архитектуру процессора.

    """

    CHOICE = "choice"
    VERSIONS = "versions"
    FILES = "files"


class ApkCB(CallbackData, prefix="apk"):  # type: ignore[misc,call-arg]
    """CallbackData для пошагового выбора APK-файла AmneziaVPN.

    Attributes
        action (ApkAction): Экран, который нужно показать.
        version (str): Ключ версии Android из конфигурации
            `modes.help.instructions.android_apk.versions` (например "11plus").
            Заполняется только для экрана `FILES`.

    """

    action: ApkAction
    version: str = ""


def device_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора устройства для помощи по настройке VPN.

    Клавиатура содержит кнопки для Android, iOS, ПК и Smart TV.
    Каждая кнопка отправляет callback_data вида `device_<тип устройства>`.

    Returns
        InlineKeyboardMarkup: Объект клавиатуры с кнопками выбора устройства.

    """
    builder = InlineKeyboardBuilder()
    buttons = [
        ("📱 Android", "device_android"),
        ("🍏 iOS", "device_ios"),
        ("💻 Windows / Linux", "device_pc"),
        ("📺 Smart TV", "device_tv"),
        ("🔀 Раздельное туннелирование", "device_split"),
        ("🔥 Happ", "device_happ"),
        ("─────────────", "noop"),
        ("👨‍💻 Связаться с разработчиком", "device_developer"),
    ]

    for text, cb in buttons:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def inline_developer_keyboard() -> InlineKeyboardMarkup:
    """Инлайн ссылка на чат с разработчиком."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Написать разработчику 💬", url="https://t.me/BorisisTheBlade"
                )
            ]
        ]
    )
    return keyboard


def android_download_kb(play_url: str) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора способа установки AmneziaVPN на Android.

    Args:
        play_url (str): Ссылка на приложение в Google Play.

    Returns
        InlineKeyboardMarkup: Кнопка Google Play и кнопка перехода
            к прямым APK-ссылкам (для тех, у кого Google Play недоступен).

    """
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Google Play", url=play_url)
    builder.button(
        text="📥 Скачать APK напрямую",
        callback_data=ApkCB(action=ApkAction.VERSIONS),
    )
    builder.adjust(1)
    return builder.as_markup()


def apk_version_kb(versions: Mapping[str, str]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора версии Android для скачивания APK.

    Args:
        versions (Mapping[str, str]): Ключ версии → подпись кнопки.
            Ключ уходит в `ApkCB.version`, поэтому должен быть коротким
            и не содержать разделитель callback_data (":").

    Returns
        InlineKeyboardMarkup: По кнопке на каждую поддерживаемую версию Android
            плюс возврат к выбору способа установки.

    """
    builder = InlineKeyboardBuilder()
    for key, title in versions.items():
        builder.button(
            text=title,
            callback_data=ApkCB(action=ApkAction.FILES, version=key),
        )
    builder.button(text="◀️ Назад", callback_data=ApkCB(action=ApkAction.CHOICE))
    builder.adjust(1)
    return builder.as_markup()


def apk_files_kb(files: Mapping[str, str]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со ссылками на APK-файлы под разные архитектуры.

    Args:
        files (Mapping[str, str]): Подпись кнопки → прямая ссылка на .apk.

    Returns
        InlineKeyboardMarkup: По кнопке-ссылке на каждый файл, в порядке
            из конфигурации (первым идёт вариант для большинства телефонов),
            плюс возврат к выбору версии Android.

    """
    builder = InlineKeyboardBuilder()
    for title, url in files.items():
        builder.button(text=title, url=url)
    builder.button(text="◀️ Назад", callback_data=ApkCB(action=ApkAction.VERSIONS))
    builder.adjust(1)
    return builder.as_markup()


async def send_link_button(bot: Bot, chat_id: int, text: str, url: str) -> None:
    """Отправляет сообщение с кликабельной кнопкой-ссылкой.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        chat_id (int): ID чата Telegram.
        text (str): Текст сообщения перед кнопкой.
        url (str): Ссылка для кнопки.

    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Скачать ⬇️", url=url)]]
    )

    await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
