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
    builder.button(text="📱 Android", callback_data="device_android")
    builder.button(text="🍏 iOS", callback_data="device_ios")
    builder.button(text="💻 Windows / Linux", callback_data="device_pc")
    builder.button(text="📺 Smart TV", callback_data="device_tv")
    builder.adjust(2, 1, 1)
    return builder.as_markup()
