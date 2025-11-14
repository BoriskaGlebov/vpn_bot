from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
        ("─────────────", "device_noop"),
        ("👨‍💻 Связаться с разработчиком", "device_developer"),
    ]

    for text, cb in buttons:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()
