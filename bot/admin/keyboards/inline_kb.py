from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_user_control_kb(user_id: int) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для управления пользователем.

    Кнопки:
        - Изменить роль
        - Управление подпиской
        - (Опционально) Заблокировать

    Args:
        user_id (int): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура с кнопками управления.

    """
    builder = InlineKeyboardBuilder()
    builder.button(text="🎭 Изменить роль", callback_data=f"user_role_change:{user_id}")
    builder.button(text="💎 Подписка", callback_data=f"user_sub_manage:{user_id}")
    # builder.button(text="❌ Заблокировать", callback_data=f"user_role_change:{user_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def role_selection_kb(user_id: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора роли пользователя.

    Кнопки:
        - User
        - Founder
        - Отмена

    Args:
        user_id (int): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура для выбора роли.

    """
    builder = InlineKeyboardBuilder()
    builder.button(text="User", callback_data=f"role_select:admin:{user_id}")
    builder.button(text="Founder", callback_data=f"role_select:founder:{user_id}")
    builder.button(text="Отмена", callback_data=f"role_cancel:{user_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


def subscription_selection_kb(user_id: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора срока подписки.

    Кнопки:
        - 1, 3, 6, 12 месяцев
        - Отмена

    Args:
        user_id (int): Telegram ID пользователя.

    Returns
        InlineKeyboardMarkup: Inline-клавиатура для выбора подписки.

    """
    builder = InlineKeyboardBuilder()
    for months in [1, 3, 6, 12]:
        builder.button(
            text=f"{months} мес.", callback_data=f"sub_select:{months}:{user_id}"
        )
    builder.button(text="Отмена", callback_data=f"sub_cancel:{user_id}")
    builder.adjust(2, 2, 1)
    return builder.as_markup()
