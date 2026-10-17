from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.core.config import settings_bot
from bot.users.enums import MainMenuText
from bot.users.utils.text_generator import vpn_button_text
from shared.enums.vpn_enum import VPNBackend


def premium_locations_kb() -> ReplyKeyboardMarkup:
    """Создаёт клавиатуру с доступными премиум-локациями.

        Формирует ReplyKeyboardMarkup, где каждая кнопка соответствует
        одной из премиум-нод (`VPNNode.premium=True`).

    Returns
        ReplyKeyboardMarkup: Клавиатура с кнопками локаций:
            - resize_keyboard=True — адаптивный размер
            - one_time_keyboard=False — клавиатура не скрывается после нажатия

    """
    builder = ReplyKeyboardBuilder()
    for location in settings_bot.vpn.premium_nodes():
        buttons = [
            KeyboardButton(text=vpn_button_text(VPNBackend.AMNEZIA, location)),
        ]
        if settings_bot.vpn.get(location).xray is not None:
            buttons.append(
                KeyboardButton(text=vpn_button_text(VPNBackend.XRAY, location))
            )

        builder.add(*buttons)
    builder.add(KeyboardButton(text=MainMenuText.BACK))
    builder.adjust(2)

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
