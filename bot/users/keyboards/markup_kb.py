from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.core.config import settings_bot
from bot.users.enums import Location, MainMenuText, VPNProtocol
from bot.users.utils.text_generator import vpn_button_text


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
        for location in Location:
            builder.row(
                KeyboardButton(text=vpn_button_text(VPNProtocol.AWG, location)),
                KeyboardButton(text=vpn_button_text(VPNProtocol.AVPN, location)),
            )
            if location.name == Location.MAIN.name and (
                settings_bot.vpn.main.xray is not None
            ):
                builder.row(
                    KeyboardButton(text=vpn_button_text(VPNProtocol.XRAY, location)),
                )
            elif settings_bot.vpn.get(location.value.lower()).xray is not None:
                builder.row(
                    KeyboardButton(text=vpn_button_text(VPNProtocol.XRAY, location)),
                )
        builder.row(
            KeyboardButton(text=MainMenuText.AMNEZIA_PROXY.value),
        )
        builder.row(KeyboardButton(text=MainMenuText.RENEW_SUBSCRIPTION.value))
    else:
        builder.row(KeyboardButton(text=MainMenuText.CHOOSE_SUBSCRIPTION.value))
        builder.row(KeyboardButton(text=MainMenuText.FREE_AMNEZIA_PROXY.value))
    builder.row(
        KeyboardButton(text=MainMenuText.CHECK_STATUS.value),
        KeyboardButton(text=MainMenuText.HELP.value),
    )
    if user_telegram_id in settings_bot.core.admin_ids:
        builder.row(KeyboardButton(text=MainMenuText.ADMIN_PANEL.value))
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
