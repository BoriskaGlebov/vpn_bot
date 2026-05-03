from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def id_link_kb(user_id: int) -> InlineKeyboardMarkup:
    """Ссылка на отправку id пользователя - администратору."""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Отправить ID админу",
                    url=f"https://t.me/BorisisTheBlade?start=id_{user_id}",
                )
            ]
        ]
    )
    return kb
