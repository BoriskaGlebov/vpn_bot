from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def proxy_url_button(url_proxy: str) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для ссылки на Proxy."""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="📨 Активировать прокси", url=url_proxy),
        InlineKeyboardButton(text="📋 Скопировать (долго жать) ссылку", url=url_proxy),
    )
    builder.adjust(1)
    return builder.as_markup()


def xray_urk_kb(url: str) -> InlineKeyboardMarkup:
    """Клавиатура со ссылкой на подписку x-ray."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📨 Долгое нажатие скопирует ссылку",
                    url=url,
                )
            ]
        ]
    )
    return keyboard
