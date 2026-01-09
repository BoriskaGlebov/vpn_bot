from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class NewsAction(StrEnum):
    """Перечисление действий пользователя при работе с новостной рассылкой.

    Attributes
        CONFIRM (str): Действие подтверждения рассылки новости.
        CANCEL (str): Действие отмены рассылки новости.

    """

    CONFIRM = "confirm"
    CANCEL = "cancel"


class NewsCB(CallbackData, prefix="news"):  # type: ignore[misc,call-arg]
    """CallbackData для подтверждения или отмены рассылки новости.

    Attributes
        action (str): Действие администратора.
            Возможные значения:
                - "confirm": подтвердить рассылку
                - "cancel": отменить рассылку

    """

    action: str


def news_confirm_kb() -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для подтверждения или отмены рассылки новости.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения и отмены.

    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Отправить",
        callback_data=NewsCB(action=NewsAction.CONFIRM),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=NewsCB(action=NewsAction.CANCEL),
    )

    return builder.as_markup()
