from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.core.config import settings_bot
from bot.users.enums import Location, PremiumLocation, VPNProtocol
from bot.users.utils.text_generator import vpn_button_text


def premium_locations_kb() -> ReplyKeyboardMarkup:
    """Создаёт клавиатуру с доступными премиум-локациями.

        Формирует ReplyKeyboardMarkup, где каждая кнопка соответствует
        одной из локаций из перечисления PremiumLocations.

    Returns
        ReplyKeyboardMarkup: Клавиатура с кнопками локаций:
            - resize_keyboard=True — адаптивный размер
            - one_time_keyboard=False — клавиатура не скрывается после нажатия

    """
    builder = ReplyKeyboardBuilder()
    for location in PremiumLocation:
        buttons = [
            KeyboardButton(text=vpn_button_text(VPNProtocol.AMNEZIA, location)),
        ]
        xray_available = (
            location.name == Location.MAIN.name
            and settings_bot.vpn.main.xray is not None
        ) or settings_bot.vpn.get(location.value.lower()).xray is not None
        if xray_available:
            buttons.append(
                KeyboardButton(text=vpn_button_text(VPNProtocol.XRAY, location))
            )

        builder.add(*buttons)
    builder.adjust(2)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
