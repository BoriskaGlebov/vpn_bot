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
        # Remnawave-подписка (один subscription-URL на все устройства)
        # показывается перед XRay-локациями — это новый "флагманский"
        # сценарий, который пользователь выбирает по умолчанию, а старые
        # кнопки по странам остаются как запасной путь.
        remnawave_enabled = (
            settings_bot.remnawave is not None and settings_bot.remnawave.enabled
        )
        if remnawave_enabled:
            builder.row(KeyboardButton(text=MainMenuText.VPN_PRO.value))
        for location in settings_bot.vpn.standard_nodes():
            node = settings_bot.vpn.get(location)
            buttons = []
            if node.amnezia_available:
                buttons.append(
                    KeyboardButton(text=vpn_button_text(VPNBackend.AMNEZIA, location)),
                )
            if node.xray_available:
                buttons.append(
                    KeyboardButton(text=vpn_button_text(VPNBackend.XRAY, location))
                )
            if buttons:
                builder.add(*buttons)
        # `adjust` переразмечает ВСЕ ранее добавленные кнопки, поэтому
        # количество первых "одиночных" строк зависит от того, была ли
        # добавлена кнопка `VPN Pro` (`PREMIUM` — всегда).
        if remnawave_enabled:
            builder.adjust(1, 1, 2)
        else:
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
