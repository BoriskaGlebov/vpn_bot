from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.config import settings_bot


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
            KeyboardButton(text="🔑 Получить VPN-конфиг AmneziaVPN"),
            KeyboardButton(text="🌐 Получить VPN-конфиг AmneziaWG"),
        )
        builder.row(KeyboardButton(text="💎 Продлить VPN-Boriska"))
    else:
        builder.row(KeyboardButton(text="💰 Выбрать подписку VPN-Boriska"))
    builder.row(
        KeyboardButton(text="📈 Проверить статус подписки"),
        KeyboardButton(text="❓ Помощь в настройке VPN"),
    )
    if user_telegram_id in settings_bot.admin_ids:
        builder.row(KeyboardButton(text="⚙️ Панель администратора"))
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )
