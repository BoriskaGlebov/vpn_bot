from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.enums import FilterTypeEnum
from bot.app_error.base_error import AppError, UserNotFoundError
from bot.config import settings_bot
from bot.database import connection
from bot.redis_service import redis_admin_mess_storage as redis_service
from bot.subscription.enums import (
    AdminPaymentAction,
    SubscriptionAction,
    ToggleSubscriptionMode,
)
from bot.subscription.keyboards.inline_kb import (
    AdminPaymentCB,
    SubscriptionCB,
    ToggleSubscriptionCB,
    admin_payment_kb,
    payment_confirm_kb,
    subscription_options_kb,
)
from bot.subscription.services import SubscriptionService
from bot.users.keyboards.markup_kb import main_kb
from bot.utils.base_router import BaseRouter
from bot.utils.start_stop_bot import edit_admin_messages, send_to_admins

m_subscription = settings_bot.messages.modes.subscription


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
                SubscriptionCB.filter(F.action == SubscriptionAction.SELECT),
            ),
        )
        self.router.callback_query.register(
            self.toggle_subscription_mode,
            and_f(
                StateFilter(SubscriptionStates.subscription_start),
                ToggleSubscriptionCB.filter(),
            ),
        )

        self.router.callback_query.register(
            self.user_paid,
            and_f(
                StateFilter(SubscriptionStates.select_period),
                SubscriptionCB.filter(F.action == SubscriptionAction.PAID),
            ),
        )
        self.router.callback_query.register(
            self.cancel_subscription, F.data == "sub_cancel"
        )
        self.router.callback_query.register(
            self.admin_confirm_payment,
            AdminPaymentCB.filter(F.action == AdminPaymentAction.CONFIRM),
        )
        self.router.callback_query.register(
            self.admin_decline_payment,
            AdminPaymentCB.filter(F.action == AdminPaymentAction.DECLINE),
        )
        # self.router.message.register(
        #     self.mistake_handler_user,
        #     and_f(
        #         or_f(
        #             StateFilter(SubscriptionStates.subscription_start),
        #             StateFilter(SubscriptionStates.select_period),
        #             StateFilter(SubscriptionStates.wait_for_paid),
        #         ),
        #         ~F.text.startswith("/"),
        #     ),
        # )

    @BaseRouter.log_method
    @connection()
    @BaseRouter.require_user
    async def start_subscription(
        self, message: Message, user: TgUser, session: AsyncSession, state: FSMContext
    ) -> None:
        """Обрабатывает начало оформления подписки.

        Args:
            user (TgUser): Пользователь Телеграм из сообщения.
            session (AsyncSession): Асинхронная сессия.
            message (Message): Сообщение пользователя, инициировавшего подписку.
            state (FSMContext): Контекст FSM для управления состояниями.

        """
        user_logger = self.logger.bind(user=user.username or user.id or "undefined")
        user_logger.info("Начало оформления подписки")
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            (
                is_premium,
                role,
                is_active_sbscr,
            ) = await self.subscription_service.check_premium(
                session=session, tg_id=user.id
            )
            if not is_premium or role == FilterTypeEnum.FOUNDER:
                text = m_subscription.start.format(
                    device_limit=settings_bot.max_configs_per_user
                )
                kb = subscription_options_kb(
                    premium=False,
                    trial=not is_active_sbscr,
                    founder=bool(role == FilterTypeEnum.FOUNDER),
                )
            else:
                text = m_subscription.premium_start.format(
                    device_limit=settings_bot.max_configs_per_user * 2
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
    @BaseRouter.require_message
    @connection()
    async def subscription_selected(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
        session: AsyncSession,
        callback_data: SubscriptionCB,
    ) -> None:
        """Обрабатывает выбор периода подписки пользователем.

        Args:
            query (CallbackQuery): Callback от Inline-кнопки с выбором подписки.
            msg (Message): Сообщение над которым надо вносить изменения.
            state (FSMContext): Контекст FSM.
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            callback_data (SubscriptionCB): Данные для работы.

        """
        user = query.from_user
        user_logger = self.logger.bind(user=user.username or user.id)
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            months = callback_data.months
            user_logger.info(f"Выбор периода подписки: {months} мес")
            price_map = settings_bot.price_map
            price = price_map.get(months)
            premium = await state.get_data()
            if price is None:
                user_logger.warning(
                    "Некорректный период подписки: %s (user_id=%s)",
                    months,
                    query.from_user.id,
                )

                await query.answer(
                    "Выбран некорректный период подписки. Пожалуйста, попробуйте ещё раз.",
                    show_alert=True,
                )

                await state.clear()
                return
            if price != 0:
                if premium.get("premium"):
                    price *= 2
                await query.answer(f"Выбрал {months} месяцев", show_alert=False)
                await msg.edit_text(
                    text=m_subscription.select_period.format(
                        premium=(
                            f"{ToggleSubscriptionMode.PREMIUM.upper()} "
                            if premium.get("premium")
                            else f"{ToggleSubscriptionMode.STANDARD.upper()} "
                        ),
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
                    await msg.delete()
                    await self.bot.send_message(
                        chat_id=query.from_user.id,
                        text=m_subscription.trial_period,
                        reply_markup=main_kb(active_subscription=True),
                    )
                    await state.clear()
                except AppError as e:
                    await query.answer(str(e.message), show_alert=True)

    @BaseRouter.log_method
    async def toggle_subscription_mode(
        self,
        query: CallbackQuery,
        state: FSMContext,
        callback_data: ToggleSubscriptionCB,
    ) -> None:
        """Переключает режим между стандартной и премиум-подпиской.

        Args:
            callback_data (ToggleSubscriptionCB): Данные для переклчения.
            query (CallbackQuery): Callback от кнопки переключения.
            state (FSMContext): Контекст FSM.

        """
        msg = query.message
        if not msg or isinstance(msg, InaccessibleMessage):
            return
        mode = callback_data.mode
        premium = mode == ToggleSubscriptionMode.PREMIUM

        text = (
            m_subscription.premium_start.format(
                device_limit=settings_bot.max_configs_per_user * 2
            )
            if premium
            else m_subscription.start
        )

        await msg.edit_text(
            text=text,
            reply_markup=subscription_options_kb(
                premium=True if premium else False, trial=True
            ),
        )
        await query.answer("")
        await state.update_data(premium=premium)

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def user_paid(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
        callback_data: SubscriptionCB,
    ) -> None:
        """Обрабатывает оплату пользователем и уведомляет админов.

        Args:
            callback_data (SubscriptionCB): Данные для формирования подписки.
            query (CallbackQuery): Callback от Inline-кнопки подтверждения оплаты.
            msg (Message): Сообщение с которым буду работать.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            await state.set_state(SubscriptionStates.wait_for_paid)
            months = callback_data.months
            price_map = settings_bot.price_map
            premium = (await state.get_data()).get("premium")
            price = price_map[months] * 2 if premium else price_map[months]

            user_logger.info(f"Пользователь нажал оплату ({months} мес, {price}₽)")
            await query.answer(f"Пользователь нажал оплату ({months} мес, {price}₽)")
            user = query.from_user

            await msg.edit_text(m_subscription.wait_for_paid.user)

            admin_message = m_subscription.wait_for_paid.admin.format(
                username=(
                    f"@{user.username}"
                    if user.username
                    else user.first_name or user.last_name or "undefined"
                ),
                user_id=user.id or "-",
                months=months,
                price=price,
                premium=(
                    f"{ToggleSubscriptionMode.PREMIUM.upper()}"
                    if premium
                    else f"{ToggleSubscriptionMode.STANDARD.upper()}"
                ),
            )
            await send_to_admins(
                bot=self.bot,
                message_text=admin_message,
                reply_markup=admin_payment_kb(
                    user_id=user.id,
                    months=months,
                    premium=premium if premium else False,
                ),
                admin_mess_storage=redis_service,
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
        msg = query.message
        if not msg or isinstance(msg, InaccessibleMessage):
            return
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            current_state = await state.get_state()
            await query.answer("Отменено ❌", show_alert=False)
            user_logger.info(f"Отмена подписки на шаге: {current_state}")
            # Если пользователь на втором шаге → вернуть к выбору периода
            if current_state == SubscriptionStates.select_period.state:
                await msg.edit_text(
                    text="Вы вернулись к выбору периода подписки ⏪",
                    reply_markup=subscription_options_kb(),
                )
                await state.set_state(SubscriptionStates.subscription_start)
                return

            # Если пользователь на первом шаге или нет состояния → выйти в главное меню
            # if msg is not None and not isinstance(msg, InaccessibleMessage):
            await msg.delete()
            await self.bot.send_message(
                chat_id=query.from_user.id,
                text="Вы отменили оформление подписки.",
            )
            await state.clear()

    @BaseRouter.log_method
    @connection()
    @BaseRouter.require_message
    async def admin_confirm_payment(
        self,
        query: CallbackQuery,
        msg: Message,
        session: AsyncSession,
        state: FSMContext,
        callback_data: AdminPaymentCB,
    ) -> None:
        """Обрабатывает подтверждение оплаты администратором.

        Args:
            callback_data (AdminPaymentCB): Данные для формирования подписки.
            query (CallbackQuery): Callback от кнопки подтверждения админом.
            msg (Message): Сообщения от пользователя для редактирования.
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(
            bot=self.bot,
            chat_id=msg.chat.id,
        ):
            await query.answer("Админ подтвердил оплату", show_alert=False)
            user_id = callback_data.user_id
            months = callback_data.months
            premium = callback_data.premium

            user_schema = await self.subscription_service.activate_paid_subscription(
                session, user_id, months, premium
            )
            user_logger.info(
                f"Админ подтвердил оплату пользователя {user_id} ({months} мес)"
            )
            if not user_schema:
                raise UserNotFoundError(tg_id=user_id)
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=m_subscription.get("accept_paid", {})
                    .get("user", "")
                    .format(
                        months=months,
                        premium=(
                            f"{ToggleSubscriptionMode.PREMIUM.upper()}"
                            if premium
                            else f"{ToggleSubscriptionMode.STANDARD.upper()}"
                        ),
                    ),
                    reply_markup=main_kb(active_subscription=True),
                )

            except TelegramBadRequest:
                await send_to_admins(
                    bot=self.bot,
                    message_text=m_subscription.accept_paid.error.format(
                        user_id=user_id
                    ),
                )

            await edit_admin_messages(
                bot=self.bot,
                user_id=user_id,
                new_text=m_subscription.get("accept_paid", {})
                .get("admin", "")
                .format(
                    user_id=user_id,
                    premium=(
                        f"{ToggleSubscriptionMode.PREMIUM.upper()}"
                        if premium
                        else f"{ToggleSubscriptionMode.STANDARD.upper()}"
                    ),
                    username=user_schema.username,
                ),
                admin_mess_storage=redis_service,
            )
            await state.clear()

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def admin_decline_payment(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
        callback_data: AdminPaymentCB,
    ) -> None:
        """Обрабатывает отклонение оплаты администратором.

        Args:
            callback_data (AdminPaymentCB): Данные для формирования подписки.
            query (CallbackQuery): Callback от кнопки отклонения админом.
            msg (Message): Сообщения для обработки.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(
            bot=self.bot,
            chat_id=msg.chat.id,
        ):
            await query.answer("Отклонено 🚫")
            user_id = callback_data.user_id
            months = callback_data.months

            user_logger.info(
                f"Админ отклонил оплату пользователя {user_id} ({months} мес)"
            )

            await self.bot.send_message(
                chat_id=user_id,
                text=m_subscription.decline_paid.user,
                reply_markup=main_kb(active_subscription=False),
            )
            await edit_admin_messages(
                bot=self.bot,
                user_id=user_id,
                new_text=m_subscription.decline_paid.admin.format(user_id=user_id),
                admin_mess_storage=redis_service,
            )
