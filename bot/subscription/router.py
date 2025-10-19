from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import bot, settings_bot
from bot.database import connection
from bot.redis_manager import redis_manager
from bot.subscription.dao import SubscriptionDAO
from bot.subscription.keyboards.inline_kb import (
    admin_payment_kb,
    payment_confirm_kb,
    subscription_options_kb,
)
from bot.users.keyboards.markup_kb import main_kb
from bot.users.schemas import SUserTelegramID
from bot.utils.start_stop_bot import edit_admin_messages, send_to_admins

subscription_router = Router()

m_subscription = settings_bot.MESSAGES["modes"]["subscription"]


class SubscriptionStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для процесса оформления подписки."""

    subscription_start: State = State()
    select_period: State = State()
    wait_for_paid: State = State()


@subscription_router.message(F.text == "💰 Выбрать подписку VPN-Boriska")  # type: ignore[misc]
async def start_subscription(message: Message, state: FSMContext) -> None:
    """Обрабатывает начало оформления подписки.

    Аргументы
        message (Message): Сообщение пользователя, инициировавшего подписку.
        state (FSMContext): Контекст FSM для управления состояниями.

    """
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        await message.answer(
            text=m_subscription["start"], reply_markup=subscription_options_kb()
        )
        await state.set_state(SubscriptionStates.subscription_start)


@subscription_router.callback_query(
    SubscriptionStates.subscription_start, lambda c: c.data.startswith("sub_select:")
)  # type: ignore[misc]
@connection()
async def subscription_selected(
    query: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Обрабатывает выбор периода подписки пользователем.

    Аргументы
        query (CallbackQuery): Callback от Inline-кнопки с выбором подписки.
        state (FSMContext): Контекст FSM.
        session (AsyncSession): Асинхронная сессия SQLAlchemy.

    """
    async with ChatActionSender.typing(bot=bot, chat_id=query.message.chat.id):
        months = int(query.data.split(":")[1])
        await query.answer(f"Выбрал {months} месяцев", show_alert=False)
        price_map = {
            1: 70,
            3: 160,
            6: 300,
            12: 600,
            14: 0,
        }
        price = price_map[months]
        if price != 0:
            await query.message.edit_text(
                text=m_subscription["select_period"].format(
                    months=months,
                    price=price,
                ),
                reply_markup=payment_confirm_kb(months),
            )
            await state.set_state(SubscriptionStates.select_period)
        else:
            await query.message.delete()
            await bot.send_message(
                chat_id=query.from_user.id,
                text=m_subscription["trial_period"],
                reply_markup=main_kb(active_subscription=True),
            )
            schema_user = SUserTelegramID(telegram_id=query.from_user.id)
            trial_days = months
            await SubscriptionDAO.activate_subscription(
                session=session, stelegram_id=schema_user, days=trial_days
            )
            await state.clear()


@subscription_router.callback_query(
    SubscriptionStates.select_period, lambda c: c.data.startswith("sub_paid:")
)  # type: ignore[misc]
async def user_paid(query: CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает оплату пользователем и уведомляет админов.

    Аргументы
        query (CallbackQuery): Callback от Inline-кнопки подтверждения оплаты.
        state (FSMContext): Контекст FSM.

    """
    async with ChatActionSender.typing(bot=bot, chat_id=query.message.chat.id):
        await query.answer()
        await state.set_state(SubscriptionStates.wait_for_paid)
        months = int(query.data.split(":")[1])
        price_map = {1: 70, 3: 160, 6: 300, 12: 600}
        price = price_map[months]
        user = query.from_user

        await query.message.edit_text(m_subscription["wait_for_paid"]["user"])

        admin_message = m_subscription["wait_for_paid"]["admin"].format(
            username=user.username or "-",
            user_id=user.id or "-",
            months=months,
            price=price,
        )
        await send_to_admins(
            bot=bot,
            message_text=admin_message,
            reply_markup=admin_payment_kb(user.id, months),
            redis_manager=redis_manager,
            telegram_id=user.id,
        )


@subscription_router.callback_query(F.data == "sub_cancel")  # type: ignore[misc]
async def cancel_subscription(query: CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает отмену оформления подписки пользователем.

    Аргументы
        query (CallbackQuery): Callback от кнопки "Отмена".
        state (FSMContext): Контекст FSM.

    """
    async with ChatActionSender.typing(bot=bot, chat_id=query.message.chat.id):
        current_state = await state.get_state()
        await query.answer("Отменено ❌", show_alert=False)

        # Если пользователь на втором шаге → вернуть к выбору периода
        if current_state == SubscriptionStates.select_period.state:
            await query.message.edit_text(
                text="Вы вернулись к выбору периода подписки ⏪",
                reply_markup=subscription_options_kb(),
            )
            await state.set_state(SubscriptionStates.subscription_start)
            return

        # Если пользователь на первом шаге или нет состояния → выйти в главное меню
        await query.message.delete()
        await bot.send_message(
            chat_id=query.from_user.id,
            text="Вы отменили оформление подписки.",
            reply_markup=main_kb(),
        )
        await state.clear()


@subscription_router.callback_query(F.data.startswith("admin_confirm:"))  # type: ignore[misc]
@connection()
async def admin_confirm_payment(
    query: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Обрабатывает подтверждение оплаты администратором.

    Аргументы
        query (CallbackQuery): Callback от кнопки подтверждения админом.
        session (AsyncSession): Асинхронная сессия SQLAlchemy.
        state (FSMContext): Контекст FSM.

    """
    async with ChatActionSender.typing(
        bot=bot,
        chat_id=query.message.chat.id,
    ):
        await query.answer("Админ подтвердил оплату", show_alert=False)
        _, user_id, months = query.data.split(":")
        user_id = int(user_id)
        months = int(months)
        schema_user = SUserTelegramID(telegram_id=user_id)
        await SubscriptionDAO.activate_subscription(
            session=session, stelegram_id=schema_user, month=months
        )

        try:
            await query.bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваша подписка на {months} мес. успешно активирована! Спасибо ❤️",
                reply_markup=main_kb(active_subscription=True),
            )
        except TelegramBadRequest:
            await send_to_admins(
                bot=bot,
                message_text=f"⚠️⚠️⚠️️️Не удалось отправить "
                f"сообщение пользователю ({user_id}) "
                f"об успешной оплате⚠️⚠️⚠️",
            )

        await edit_admin_messages(
            bot=bot,
            user_id=user_id,
            new_text=f"✅ Оплата от пользователя <code>{user_id}</code> подтверждена.\nПодписка активирована.",
            redis_manager=redis_manager,
        )


@subscription_router.callback_query(F.data.startswith("admin_decline:"))  # type: ignore[misc]
async def admin_decline_payment(query: CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает отклонение оплаты администратором.

    Аргументы
        query (CallbackQuery): Callback от кнопки отклонения админом.
        state (FSMContext): Контекст FSM.

    """
    async with ChatActionSender.typing(
        bot=bot,
        chat_id=query.message.chat.id,
    ):
        await query.answer("Отклонено 🚫")
        _, user_id, months = query.data.split(":")
        user_id = int(user_id)
        months = int(months)

        # Сообщаем пользователю
        try:
            await query.bot.send_message(
                chat_id=user_id,
                text="❌ Оплата не подтверждена. Если вы уверены, что оплата была, свяжитесь с поддержкой.",
                reply_markup=main_kb(active_subscription=False),
            )
        except TelegramBadRequest:
            pass
        await edit_admin_messages(
            bot=bot,
            user_id=user_id,
            new_text=f"🚫 Оплата от пользователя <code>{user_id}</code> отклонена.",
            redis_manager=redis_manager,
        )
