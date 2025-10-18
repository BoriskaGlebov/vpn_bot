from admin.keyboards.inline_kb import (
    admin_user_control_kb,
    role_selection_kb,
    subscription_selection_kb,
)
from aiogram import Router
from aiogram.types import CallbackQuery

admin_router = Router()


@admin_router.callback_query(lambda c: c.data and c.data.startswith("user_"))  # type: ignore[misc]
async def admin_action_callback(query: CallbackQuery) -> None:
    """Дейставия с ноывм пользователем."""
    user_id = int(query.data.split(":")[1])
    old_text = query.message.text
    if query.data.startswith("user_role_change"):
        await query.message.edit_text(
            f"{old_text}\n {'*' * 10}\nВыберите новую роль для пользователя:",
            reply_markup=role_selection_kb(user_id),
        )
    elif query.data.startswith("user_sub_manage"):
        await query.message.edit_text(
            f"{old_text}\n{'*' * 10}\nВыберите срок подписки для пользователя:",
            reply_markup=subscription_selection_kb(user_id),
        )
    elif query.data.startswith("user_block"):
        # Здесь можно заблокировать пользователя
        await query.message.edit_text("Пользователь заблокирован.")


# Обработка выбора роли
@admin_router.callback_query(lambda c: c.data and c.data.startswith("role_select"))  # type: ignore[misc]
async def role_select_callback(query: CallbackQuery) -> None:
    """Менять роли пользователя."""
    _, role_name, user_id = query.data.split(":")
    user_id = int(user_id)

    # Тут нужно вызвать DAO для изменения роли пользователя
    # await UserDAO.add_role(session, SRole(name=role_name), SUser(telegram_id=user_id))
    old_text = query.message.text.split("********")[1]
    await query.message.edit_text(
        f"{old_text}\n{'*' * 10}\nРоль пользователя изменена на {role_name} ✅",
        reply_markup=admin_user_control_kb(user_id),
    )


# Обработка выбора подписки
@admin_router.callback_query(lambda c: c.data and c.data.startswith("sub_select"))  # type: ignore[misc]
async def sub_select_callback(query: CallbackQuery) -> None:
    """Менять срок подписки."""
    _, months, user_id = query.data.split(":")
    user_id = int(user_id)
    months = int(months)

    # Тут нужно вызвать DAO для активации подписки
    # await SubscriptionDAO.activate(user_id=user_id, days=months*30)
    old_text = query.message.text.split("********")[1]
    await query.message.edit_text(
        f"{old_text}\n"
        f"{'*' * 10}\n"
        f"Подписка пользователя активирована на {months} месяц(ев) ✅",
        reply_markup=admin_user_control_kb(user_id),
    )


#
