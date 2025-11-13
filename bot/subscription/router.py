from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.redis_manager import redis_manager
from bot.subscription.keyboards.inline_kb import (
    admin_payment_kb,
    payment_confirm_kb,
    subscription_options_kb,
)
from bot.subscription.services import SubscriptionService
from bot.users.keyboards.markup_kb import main_kb
from bot.utils.base_router import BaseRouter
from bot.utils.start_stop_bot import edit_admin_messages, send_to_admins

m_subscription = settings_bot.MESSAGES["modes"]["subscription"]


# TODO не хватает момента когда срок истекает, что б и не уудалалялась подписка но и внопка олпатить появлялась


class SubscriptionStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для процесса оформления подписки."""

    subscription_start: State = State()
    select_period: State = State()
    wait_for_paid: State = State()


class SubscriptionRouter(BaseRouter):
    """Роутер для управления процессом подписки пользователей."""

    def __init__(
        self, bot: Bot, logger: Logger, subscription_service: SubscriptionService
    ) -> None:
        super().__init__(bot, logger)
        self.subscription_service = subscription_service

    def _register_handlers(self) -> None:
        self.router.message.register(
            self.start_subscription,
            or_f(
                F.text == "💰 Выбрать подписку VPN-Boriska",
                F.text == "💎 Продлить VPN-Boriska",
            ),
        )
        self.router.callback_query.register(
            self.subscription_selected,
            and_f(
                StateFilter(SubscriptionStates.subscription_start),
                F.data.startswith("sub_select:"),
            ),
        )
        self.router.callback_query.register(
            self.toggle_subscription_mode,
            and_f(
                StateFilter(SubscriptionStates.subscription_start),
                F.data.startswith("sub_toggle:"),
            ),
        )

        self.router.callback_query.register(
            self.user_paid,
            and_f(
                StateFilter(SubscriptionStates.select_period),
                F.data.startswith("sub_paid:"),
            ),
        )
        self.router.callback_query.register(
            self.cancel_subscription, F.data == "sub_cancel"
        )
        self.router.callback_query.register(
            self.admin_confirm_payment, F.data.startswith("admin_confirm:")
        )
        self.router.callback_query.register(
            self.admin_decline_payment, F.data.startswith("admin_decline:")
        )

    @BaseRouter.log_method
    @connection()
    async def start_subscription(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        """Обрабатывает начало оформления подписки.

        Args:
            session (AsyncSession): Асинхронная сессия.
            message (Message): Сообщение пользователя, инициировавшего подписку.
            state (FSMContext): Контекст FSM для управления состояниями.

        """
        user_logger = self.logger.bind(
            user=message.from_user.username or message.from_user.id
        )
        user_logger.info("Начало оформления подписки")
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            (
                is_premium,
                role,
                is_active_sbscr,
            ) = await self.subscription_service.check_premium(
                session=session, tg_id=message.from_user.id
            )
            print(is_premium)
            print(role)
            print(is_active_sbscr)
            if not is_premium or role == "founder":
                text = m_subscription.get("start", "").format(
                    device_limit=settings_bot.MAX_CONFIGS_PER_USER
                )
                kb = subscription_options_kb(premium=False, trial=not is_active_sbscr)
            else:
                text = m_subscription.get("premium_start", "").format(
                    device_limit=settings_bot.MAX_CONFIGS_PER_USER * 2
                )
                kb = subscription_options_kb(
                    premium=is_premium, trial=not is_active_sbscr
                )
                await state.update_data(premium=is_premium)
            await message.answer(
                text=text,
                reply_markup=kb,
            )
            await state.set_state(SubscriptionStates.subscription_start)
            await state.update_data({})

    @BaseRouter.log_method
    @connection()
    async def subscription_selected(
        self, query: CallbackQuery, state: FSMContext, session: AsyncSession
    ) -> None:
        """Обрабатывает выбор периода подписки пользователем.

        Args:
            query (CallbackQuery): Callback от Inline-кнопки с выбором подписки.
            state (FSMContext): Контекст FSM.
            session (AsyncSession): Асинхронная сессия SQLAlchemy.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.message.chat.id):
            months = int(query.data.split(":")[1])
            user_logger.info(f"Выбор периода подписки: {months} мес")
            price_map = settings_bot.PRICE_MAP
            price = price_map[months]
            premium = await state.get_data()
            if price != 0:
                if premium.get("premium"):
                    price *= 2
                await query.answer(f"Выбрал {months} месяцев", show_alert=False)
                await query.message.edit_text(
                    text=m_subscription["select_period"].format(
                        premium="PREMIUM " if premium else "STANDARD ",
                        months=months,
                        price=price,
                    ),
                    reply_markup=payment_confirm_kb(months),
                )
                await state.set_state(SubscriptionStates.select_period)
            else:
                days = months  # для триала количество дней
                try:
                    await self.subscription_service.start_trial_subscription(
                        session=session, user_id=query.from_user.id, days=days
                    )
                    await query.answer("Выбрал пробный период", show_alert=False)
                    await query.message.delete()
                    await self.bot.send_message(
                        chat_id=query.from_user.id,
                        text=m_subscription["trial_period"],
                        reply_markup=main_kb(active_subscription=True),
                    )
                    await state.clear()
                except ValueError as e:
                    await query.answer(str(e), show_alert=True)

    @BaseRouter.log_method
    async def toggle_subscription_mode(
        self, query: CallbackQuery, state: FSMContext
    ) -> None:
        """Переключает режим между стандартной и премиум-подпиской.

        Args:
            query (CallbackQuery): Callback от кнопки переключения.
            state (FSMContext): Контекст FSM.

        """
        mode = query.data.split(":")[1]
        premium = mode == "premium"

        text = (
            m_subscription.get("premium_start", "премиум текст").format(
                device_limit=settings_bot.MAX_CONFIGS_PER_USER * 2
            )
            if premium
            else m_subscription["start"]
        )

        await query.message.edit_text(
            text=text,
            reply_markup=subscription_options_kb(premium=premium),
        )
        await query.answer("")
        await state.update_data(premium=premium)

    @BaseRouter.log_method
    async def user_paid(self, query: CallbackQuery, state: FSMContext) -> None:
        """Обрабатывает оплату пользователем и уведомляет админов.

        Args:
            query (CallbackQuery): Callback от Inline-кнопки подтверждения оплаты.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.message.chat.id):
            await state.set_state(SubscriptionStates.wait_for_paid)
            months = int(query.data.split(":")[1])
            price_map = settings_bot.PRICE_MAP
            premium = (await state.get_data()).get("premium")
            price = price_map[months] * 2 if premium else price_map[months]

            user_logger.info(f"Пользователь нажал оплату ({months} мес, {price}₽)")
            await query.answer(f"Пользователь нажал оплату ({months} мес, {price}₽)")
            user = query.from_user

            await query.message.edit_text(m_subscription["wait_for_paid"]["user"])

            admin_message = m_subscription["wait_for_paid"]["admin"].format(
                username=(
                    f"@{user.username}"
                    if user.username
                    else user.first_name or user.last_name or "undefined"
                ),
                user_id=user.id or "-",
                months=months,
                price=price,
                premium="PREMIUM" if premium else "STANDARD",
            )
            await send_to_admins(
                bot=self.bot,
                message_text=admin_message,
                reply_markup=admin_payment_kb(user.id, months, premium),
                redis_manager=redis_manager,
                telegram_id=user.id,
            )

    @BaseRouter.log_method
    async def cancel_subscription(
        self, query: CallbackQuery, state: FSMContext
    ) -> None:
        """Обрабатывает отмену оформления подписки пользователем.

        Args:
            query (CallbackQuery): Callback от кнопки "Отмена".
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.message.chat.id):
            current_state = await state.get_state()
            await query.answer("Отменено ❌", show_alert=False)
            user_logger.info(f"Отмена подписки на шаге: {current_state}")
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
            await self.bot.send_message(
                chat_id=query.from_user.id,
                text="Вы отменили оформление подписки.",
            )
            await state.clear()

    @BaseRouter.log_method
    @connection()
    async def admin_confirm_payment(
        self, query: CallbackQuery, session: AsyncSession, state: FSMContext
    ) -> None:
        """Обрабатывает подтверждение оплаты администратором.

        Args:
            query (CallbackQuery): Callback от кнопки подтверждения админом.
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(
            bot=self.bot,
            chat_id=query.message.chat.id,
        ):
            await query.answer("Админ подтвердил оплату", show_alert=False)
            _, user_id, months, premium = query.data.split(":")
            user_id, months, premium = (
                int(user_id),
                int(months),
                True if premium == "True" else False,
            )
            user_model = await self.subscription_service.activate_paid_subscription(
                session, user_id, months, premium
            )
            user_logger.info(
                f"Админ подтвердил оплату пользователя {user_id} ({months} мес)"
            )
            if not user_model:
                raise ValueError(f"Не нашел пользователя с {user_id}")

            try:
                await query.bot.send_message(
                    chat_id=user_id,
                    text=m_subscription.get("accept_paid", {})
                    .get("user", "")
                    .format(
                        months=months,
                        premium=user_model.subscription.type.value.upper(),
                    ),
                    reply_markup=main_kb(active_subscription=True),
                )
            except TelegramBadRequest:
                await send_to_admins(
                    bot=self.bot,
                    message_text=m_subscription.get("accept_paid", {})
                    .get("error", "")
                    .format(user_id=user_id),
                )

            await edit_admin_messages(
                bot=self.bot,
                user_id=user_id,
                new_text=m_subscription.get("accept_paid", {})
                .get("admin", "")
                .format(
                    user_id=user_id,
                    premium="PREMIUM" if premium else "STANDARD",
                    username=user_model.username,
                ),
                redis_manager=redis_manager,
            )

    @BaseRouter.log_method
    async def admin_decline_payment(
        self, query: CallbackQuery, state: FSMContext
    ) -> None:
        """Обрабатывает отклонение оплаты администратором.

        Args:
            query (CallbackQuery): Callback от кнопки отклонения админом.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(
            bot=self.bot,
            chat_id=query.message.chat.id,
        ):
            await query.answer("Отклонено 🚫")
            _, user_id, months, premium = query.data.split(":")
            user_id = int(user_id)
            months = int(months)
            user_logger.info(
                f"Админ отклонил оплату пользователя {user_id} ({months} мес)"
            )
            # Сообщаем пользователю
            try:
                await query.bot.send_message(
                    chat_id=user_id,
                    text=m_subscription.get("decline_paid", {}).get("user", ""),
                    reply_markup=main_kb(active_subscription=False),
                )
            except TelegramBadRequest:
                pass
            await edit_admin_messages(
                bot=self.bot,
                user_id=user_id,
                new_text=m_subscription.get("decline_paid", {})
                .get("admin", "")
                .format(user_id=user_id),
                redis_manager=redis_manager,
            )
