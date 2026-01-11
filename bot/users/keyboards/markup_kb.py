from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.config import settings_bot
from bot.users.enums import MainMenuText


def main_kb(
    active_subscription: bool = False,
    user_telegram_id: int | None = None,
) -> ReplyKeyboardMarkup:
    """Формирует клавиатуру главного меню бота.

    Args:
        active_subscription (bool): Подписка активна или нет
        user_telegram_id (Optional[int]): Telegram ID пользователя, который вызывает клавиатуру.
            Если None, отображаются только обычные пользовательские кнопки.

    Returns
        ReplyKeyboardMarkup: Клавиатура для пользователя.

    """
    builder = ReplyKeyboardBuilder()
    if active_subscription:
        builder.row(
            KeyboardButton(text=MainMenuText.AMNEZIA_VPN.value),
            KeyboardButton(text=MainMenuText.AMNEZIA_WG.value),
        )
        builder.row(KeyboardButton(text=MainMenuText.RENEW_SUBSCRIPTION.value))
    else:
        builder.row(KeyboardButton(text=MainMenuText.CHOOSE_SUBSCRIPTION.value))
    builder.row(
        KeyboardButton(text=MainMenuText.CHECK_STATUS.value),
        KeyboardButton(text=MainMenuText.HELP.value),
    )
    if user_telegram_id in settings_bot.admin_ids:
        builder.row(KeyboardButton(text=MainMenuText.ADMIN_PANEL.value))
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
