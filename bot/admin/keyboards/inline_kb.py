from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.admin.enums import ActionEnum, FilterTypeEnum
from bot.config import settings_bot


class UserPageCB(CallbackData, prefix="pagination_user"):  # type: ignore[misc,call-arg]
    """Callback-данные для управления пользователями на странице администратора.

    Attributes
        filter_type (str): Тип фильтра (например, 'admin', 'user', 'founder').
        index (int): Индекс пользователя в текущем списке.
        action (str): Действие, связанное с пользователем
            ('next', 'prev', 'role_change', 'sub_manage' и т.д.).
        telegram_id (int | None): Telegram ID пользователя (опционально).
        month (int): Количество месяцев для подписки (опционально).

    """

    filter_type: str
    index: int
    action: str
    telegram_id: int | None = None
    month: int = 0


def common_user_buttons(
    builder: InlineKeyboardBuilder,
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> None:
    """Общие кнопки смены ролей и срока подписки."""
    builder.button(
        text="🎭 Роль",
        callback_data=UserPageCB(
            filter_type=filter_type,
            index=index,
            action=ActionEnum.ROLE_CHANGE,
            telegram_id=telegram_id,
        ),
    )
    builder.button(
        text="💎 Срок подписки",
        callback_data=UserPageCB(
            filter_type=filter_type,
            index=index,
            action=ActionEnum.SUB_MANAGE,
            telegram_id=telegram_id,
        ),
    )


def admin_user_control_kb(
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для управления пользователем.

    Args:
        filter_type (str): Тип фильтра, определяющий категорию пользователей.
        index (int, optional): Индекс текущего пользователя. По умолчанию 0.
        telegram_id (int | None, optional): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками управления пользователем.

    """
    builder = InlineKeyboardBuilder()

    common_user_buttons(builder, filter_type, index, telegram_id)

    builder.adjust(2, 1, 1)
    return builder.as_markup()


def role_selection_kb(
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для выбора роли пользователя.

    Args:
        filter_type (str): Текущий фильтр пользователей.
        index (int, optional): Индекс текущего пользователя. По умолчанию 0.
        telegram_id (int | None, optional): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Клавиатура для выбора роли.

    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="User",
        callback_data=UserPageCB(
            filter_type="user",
            index=index,
            action=ActionEnum.ROLE_SELECT,
            telegram_id=telegram_id,
        ),
    )
    builder.button(
        text="Founder",
        callback_data=UserPageCB(
            filter_type="founder",
            index=index,
            action=ActionEnum.ROLE_SELECT,
            telegram_id=telegram_id,
        ),
    )
    builder.button(
        text="Отмена",
        callback_data=UserPageCB(
            filter_type=filter_type,
            index=index,
            action=ActionEnum.ROLE_CANCEL,
            telegram_id=telegram_id,
        ),
    )

    builder.adjust(2, 1)
    return builder.as_markup()


def subscription_selection_kb(
    filter_type: str,
    index: int = 0,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для выбора срока подписки.

    Args:
        filter_type (str): Текущий фильтр пользователей.
        index (int, optional): Индекс текущего пользователя. По умолчанию 0.
        telegram_id (int | None, optional): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Клавиатура для выбора длительности подписки.

    """
    builder = InlineKeyboardBuilder()

    for months in list(settings_bot.price_map.keys())[:-1]:
        builder.button(
            text=f"{months} мес.",
            callback_data=UserPageCB(
                filter_type=filter_type,
                index=index,
                action="sub_select",
                telegram_id=telegram_id,
                month=months,
            ),
        )

    builder.button(
        text="Отмена",
        callback_data=UserPageCB(
            filter_type=filter_type,
            index=index,
            action=ActionEnum.SUBSCR_CANCEL,
            telegram_id=telegram_id,
        ),
    )

    builder.adjust(2, 2, 1)
    return builder.as_markup()


class AdminCB(CallbackData, prefix="admin"):  # type: ignore[misc,call-arg]
    """Callback-данные для фильтрации пользователей в админ-панели.

    Attributes
        filter_type (str): Тип фильтра (например, 'admin', 'founder', 'user').

    """

    filter_type: str


def admin_main_kb() -> InlineKeyboardMarkup:
    """Создаёт основную клавиатуру панели администратора.

    Returns
        InlineKeyboardMarkup: Клавиатура с фильтрами пользователей.

    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="👑 Админы", callback_data=AdminCB(filter_type=FilterTypeEnum.ADMIN)
    )
    builder.button(
        text="🏗 Основатели", callback_data=AdminCB(filter_type=FilterTypeEnum.FOUNDER)
    )
    builder.button(
        text="🙂 Обычные пользователи",
        callback_data=AdminCB(filter_type=FilterTypeEnum.USER),
    )

    builder.adjust(1)
    return builder.as_markup()


def user_navigation_kb(
    filter_type: str,
    index: int,
    total: int,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для навигации между пользователями.

    Args:
        filter_type (str): Текущий фильтр пользователей.
        index (int): Индекс текущего пользователя.
        total (int): Общее количество пользователей.
        telegram_id (int | None, optional): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками навигации и управления.

    """
    builder = InlineKeyboardBuilder()

    common_user_buttons(builder, filter_type, index, telegram_id)

    if index > 0:
        builder.button(
            text="⬅️ Назад",
            callback_data=UserPageCB(
                filter_type=filter_type,
                index=index - 1,
                action=ActionEnum.NAVIGATE,
                telegram_id=telegram_id,
            ),
        )

    if index < total - 1:
        builder.button(
            text="➡️ Вперёд",
            callback_data=UserPageCB(
                filter_type=filter_type,
                index=index + 1,
                action=ActionEnum.NAVIGATE,
                telegram_id=telegram_id,
            ),
        )

    builder.adjust(2, 1)
    return builder.as_markup()
