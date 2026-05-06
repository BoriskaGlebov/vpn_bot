from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.core.config import settings_bot
from bot.users.enums import PremiumLocation, VPNProtocol
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
        builder.row(
            KeyboardButton(text=vpn_button_text(VPNProtocol.AWG, location)),
            KeyboardButton(text=vpn_button_text(VPNProtocol.AVPN, location)),
        )
        if settings_bot.vpn.nodes.get(location.value.lower()).xray is not None:
            builder.row(
                KeyboardButton(text=vpn_button_text(VPNProtocol.XRAY, location)),
            )

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
