from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def referral_kb(bot_name: str, tg_id: int) -> InlineKeyboardMarkup:
    """ссылка приглашение для получения бонуса за приведенного подписчика."""
    ref_link = f"https://t.me/{bot_name}?start=ref_{tg_id}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📨 Долгое нажатие скопирует ссылку",
                    url=ref_link,
                )
            ]
        ]
    )
    return keyboard
