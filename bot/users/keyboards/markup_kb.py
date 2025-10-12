from typing import Optional

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.config import settings_bot


def main_kb(user_telegram_id: Optional[int] = None) -> ReplyKeyboardMarkup:
    """Формирует клавиатуру главного меню бота с дружелюбными подписями и эмодзи.

    Args:
        user_telegram_id (Optional[int]): Telegram ID пользователя, который вызывает клавиатуру.
            Если None, отображаются только обычные пользовательские кнопки.

    Returns
        ReplyKeyboardMarkup: Клавиатура для пользователя.

    Пример использования:
        user_telegram_id = 123456789
        keyboard = main_kb(user_telegram_id)
        await message.answer("Выберите действие:", reply_markup=keyboard)

    """
    kb_list = [
        [KeyboardButton(text="🔑 Получить VPN-конфиг AmneziaVPN")],
        [KeyboardButton(text="🌐 Получить VPN-конфиг AmneziaWG")],
        [KeyboardButton(text="📈 Проверить статус подписки")],
        [KeyboardButton(text="❓ Помощь в настройке VPN")],
    ]

    if user_telegram_id in settings_bot.ADMIN_IDS:
        kb_list.append([KeyboardButton(text="⚙️ Панель администратора")])

    keyboard = ReplyKeyboardMarkup(
        keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True
    )

    return keyboard
