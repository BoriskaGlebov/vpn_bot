from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.core.config import settings_bot
from bot.users.enums import MainMenuText
from bot.users.utils.text_generator import vpn_button_text
from shared.enums.vpn_enum import VPNBackend


def main_kb(
    active_subscription: bool = False,
    user_telegram_id: int | None = None,
    premium_access: bool = False,
) -> ReplyKeyboardMarkup:
    """Формирует клавиатуру главного меню бота.

    Args:
        premium_access: проверка, премиум пользователя
        active_subscription (bool): Подписка активна или нет
        user_telegram_id (Optional[int]): Telegram ID пользователя, который вызывает клавиатуру.
            Если None, отображаются только обычные пользовательские кнопки.

    Returns
        ReplyKeyboardMarkup: Клавиатура для пользователя.

    """
    builder = ReplyKeyboardBuilder()
    if active_subscription:
        builder.row(
            KeyboardButton(text=MainMenuText.PREMIUM.value),
        )
        for location in settings_bot.vpn.standard_nodes():
            buttons = [
                KeyboardButton(text=vpn_button_text(VPNBackend.AMNEZIA, location)),
            ]
            if settings_bot.vpn.get(location).xray is not None:
                buttons.append(
                    KeyboardButton(text=vpn_button_text(VPNBackend.XRAY, location))
                )
            builder.add(*buttons)
        builder.adjust(1, 2)
    subscription_button_text = (
        MainMenuText.MY_SUBSCRIPTION.value
        if active_subscription
        else MainMenuText.GET_SUBSCRIPTION.value
    )
    builder.row(KeyboardButton(text=subscription_button_text))
    # builder.row(KeyboardButton(text=MainMenuText.HELP.value))
    if user_telegram_id in settings_bot.core.admin_ids:
        builder.row(KeyboardButton(text=MainMenuText.ADMIN_PANEL.value))
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
    )
