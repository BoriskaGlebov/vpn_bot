from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def device_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора устройства для помощи по настройке VPN.

    Клавиатура содержит кнопки для Android, iOS, ПК и Smart TV.
    Каждая кнопка отправляет callback_data вида `device_<тип устройства>`.

    Returns
        InlineKeyboardMarkup: Объект клавиатуры с кнопками выбора устройства.

    """
    builder = InlineKeyboardBuilder()
    buttons = [
        ("📱 Android", "device_android"),
        ("🍏 iOS", "device_ios"),
        ("💻 Windows / Linux", "device_pc"),
        ("📺 Smart TV", "device_tv"),
        ("🔀 Раздельное туннелирование", "device_split"),
        ("─────────────", "device_noop"),
        ("👨‍💻 Связаться с разработчиком", "device_developer"),
    ]

    for text, cb in buttons:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def inline_developer_keyboard() -> InlineKeyboardMarkup:
    """Инлайн ссылка на чат с разработчиком."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Написать разработчику 💬", url="https://t.me/BorisisTheBlade"
                )
            ]
        ]
    )
    return keyboard


async def send_link_button(bot: Bot, chat_id: int, text: str, url: str) -> None:
    """Отправляет сообщение с кликабельной кнопкой-ссылкой.

    Args:
        bot (Bot): Экземпляр бота Aiogram.
        chat_id (int): ID чата Telegram.
        text (str): Текст сообщения перед кнопкой.
        url (str): Ссылка для кнопки.

    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Скачать ⬇️", url=url)]]
    )

    await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
