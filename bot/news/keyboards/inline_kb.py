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


class TargetAction(StrEnum):
    """Тип получателя рассылки новости.

    Attributes
        ALL: Отправка всем пользователям.
        ONE: Отправка конкретному пользователю по user_id.

    """

    ALL = "all"
    ONE = "one"


class NewsCB(CallbackData, prefix="news"):  # type: ignore[misc,call-arg]
    """Callback данные для подтверждения или отмены рассылки новости.

    Attributes
        action: Действие администратора.
            Возможные значения:
            - NewsAction.CONFIRM — подтвердить отправку
            - NewsAction.CANCEL — отменить отправку

    """

    action: str


class TargetCB(CallbackData, prefix="target"):  # type: ignore[misc,call-arg]
    """Callback данные выбора типа получателя рассылки.

    Attributes
        target: Тип получателя.
            Возможные значения:
            - TargetAction.ALL — всем пользователям
            - TargetAction.ONE — конкретному пользователю

    """

    target: str


def news_confirm_kb() -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру подтверждения отправки новости.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками:
            - "Отправить" (подтвердить рассылку)
            - "Отмена" (отменить рассылку)

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


def target_choice_kb() -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру выбора получателя рассылки.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками:
            - "Всем" (рассылка всем пользователям)
            - "Пользователю по ID" (персональная отправка)

    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="Всем",
        callback_data=TargetCB(target=TargetAction.ALL),
    )
    builder.button(
        text="Пользователю по ID",
        callback_data=TargetCB(target=TargetAction.ONE),
    )

    return builder.as_markup()
