from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.vpn.enums import PremiumLocations


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
    for location in PremiumLocations:
        builder.row(
            KeyboardButton(text=location.value),
        )

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
