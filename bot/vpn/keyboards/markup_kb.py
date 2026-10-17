from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.core.config import settings_bot
from bot.users.enums import MainMenuText, VPNProtocol, available_premium_locations
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
    for location in available_premium_locations():
        buttons = [
            KeyboardButton(text=vpn_button_text(VPNProtocol.AMNEZIA, location)),
        ]
        if settings_bot.vpn.get(location.value).xray is not None:
            buttons.append(
                KeyboardButton(text=vpn_button_text(VPNProtocol.XRAY, location))
            )

        builder.add(*buttons)
    builder.add(KeyboardButton(text=MainMenuText.BACK))
    builder.adjust(2)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
