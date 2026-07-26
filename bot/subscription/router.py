from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import (
    MessageNotFoundError,
    SubscriptionActivationFailedError,
    TransactionIdMissingError,
)
from bot.core.config import settings_bot
from bot.core.filters import IsAdmin
from bot.redis_service import RedisAdminMessageStorage
from bot.referrals.schemas import GrantReferralBonusResponse
from bot.referrals.services import ReferralService
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
from bot.subscription.utils.sub_utils import get_correct_price_map, get_correct_sub_type
from bot.users.enums import MainMenuText
from bot.users.keyboards.markup_kb import main_kb
from bot.utils.base_router import BaseRouter
from bot.utils.formatting import format_username
from bot.utils.start_stop_bot import edit_admin_messages, send_to_admins
from shared.enums.admin_enum import FilterTypeEnum

m_subscription = settings_bot.messages.modes.subscription

# TODO дать возможность удалять свои конфиг файлы
# TODO добавлен платежный сервис надо учесть это в логах, тестах и все такое


class SubscriptionStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для процесса оформления подписки."""

    subscription_start: State = State()
    select_period: State = State()
    wait_for_paid: State = State()


class SubscriptionRouter(BaseRouter):
    """Роутер для управления процессом подписки пользователей."""

    price_map = settings_bot.pricing

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        redis_service: RedisAdminMessageStorage,
    ) -> None:
        super().__init__(bot, logger)
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self.redis_service = redis_service

    def _register_handlers(self) -> None:
        is_admin = IsAdmin()
        self.router.message.register(
            self.start_subscription,
            or_f(
                F.text == MainMenuText.CHOOSE_SUBSCRIPTION,
                F.text == MainMenuText.RENEW_SUBSCRIPTION,
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
            self.cancel_subscription,
            SubscriptionCB.filter(F.action == SubscriptionAction.CANCEL),
        )
        self.router.callback_query.register(
            self.admin_confirm_payment,
            AdminPaymentCB.filter(F.action == AdminPaymentAction.CONFIRM),
            is_admin,
        )
        self.router.callback_query.register(
            self.admin_decline_payment,
            AdminPaymentCB.filter(F.action == AdminPaymentAction.DECLINE),
            is_admin,
        )
        self.router.message.register(
            self.mistake_handler_user,
            and_f(
                or_f(
                    StateFilter(SubscriptionStates.subscription_start),
                    StateFilter(SubscriptionStates.select_period),
                    StateFilter(SubscriptionStates.wait_for_paid),
                ),
                ~F.text.startswith("/"),
            ),
        )
        self.router.message.register(
            self.check_subscription,
            F.text == MainMenuText.CHECK_STATUS.value,
        )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def start_subscription(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Обрабатывает начало оформления подписки.

        Args:
            user (TgUser): Пользователь Телеграм из сообщения.
            message (Message): Сообщение пользователя, инициировавшего подписку.
            state (FSMContext): Контекст FSM для управления состояниями.

        """
        user_logger = self.logger.bind(user=format_username(user))
        user_logger.info("Начало оформления подписки")
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            (
                is_premium,
                role,
                is_active_sbscr,
                used_trial,
            ) = await self.subscription_service.check_premium(tg_id=user.id)
            await message.answer(
                text="Начнем оформление подписки", reply_markup=ReplyKeyboardRemove()
            )
            founder = role == FilterTypeEnum.FOUNDER
            if founder:
                text = m_subscription.founder_start.format(
                    device_limit=settings_bot.core.max_configs_per_user * 2,
                    month=self.price_map.price_map_founder.get(1, 0),
                    quarter=self.price_map.price_map_founder.get(3, 0),
                    half_year=self.price_map.price_map_founder.get(6, 0),
                    year=self.price_map.price_map_founder.get(12, 0),
                )
                kb = subscription_options_kb(
                    premium=False,
                    trial=True,  # нечего им смотреть на триал, помечаю что использовал.
                    founder=True,
                )
            elif not is_premium:
                text = m_subscription.start.format(
                    device_limit=settings_bot.core.max_configs_per_user,
                    month=self.price_map.price_map.get(1, 0),
                    quarter=self.price_map.price_map.get(3, 0),
                    half_year=self.price_map.price_map.get(6, 0),
                    year=self.price_map.price_map.get(12, 0),
                )
                kb = subscription_options_kb(
                    premium=False,
                    trial=used_trial,
                )
            else:
                text = m_subscription.premium_start.format(
                    device_limit=settings_bot.core.max_configs_per_user * 2,
                    month=self.price_map.price_map_premium.get(1, 0),
                    quarter=self.price_map.price_map_premium.get(3, 0),
                    half_year=self.price_map.price_map_premium.get(6, 0),
                    year=self.price_map.price_map_premium.get(12, 0),
                )
                kb = subscription_options_kb(premium=is_premium, trial=used_trial)
            # Сохраняем контекст сессии оформления подписки целиком (не только
            # premium) — иначе при возврате назад с экрана оплаты (cancel_subscription)
            # founder/used_trial теряются и пользователю показываются чужие цены.
            await state.update_data(
                premium=is_premium, founder=founder, used_trial=used_trial
            )
            await message.answer(
                text=text,
                reply_markup=kb,
            )
            await state.set_state(SubscriptionStates.subscription_start)

    # TODO добавлен платежный сервис
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def subscription_selected(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
        callback_data: SubscriptionCB,
    ) -> None:
        """Обрабатывает выбор периода подписки пользователем.

        Args:
            query (CallbackQuery): Callback от Inline-кнопки с выбором подписки.
            msg (Message): Сообщение над которым надо вносить изменения.
            state (FSMContext): Контекст FSM.
            callback_data (SubscriptionCB): Данные для работы.

        """
        user = query.from_user
        user_logger = self.logger.bind(user=format_username(user))
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            months = callback_data.months
            founder = callback_data.founder
            user_logger.info(f"Выбор периода подписки: {months} мес")
            data = await state.get_data()
            is_premium = data.get("premium", False)
            if months != 7:  # Проверка на триал.
                price_map = get_correct_price_map(premium=is_premium, founder=founder)
                sub_type = get_correct_sub_type(premium=is_premium, founder=founder)
                price = price_map[months]
                transaction_info = await self.subscription_service.create_transaction(
                    amount=price,
                    subscription_months=months,
                    is_premium=is_premium,
                    is_founder=founder,
                )

                await query.answer(f"Выбрал {months} месяцев", show_alert=False)

                await msg.edit_text(
                    text=m_subscription.select_period.format(
                        sub_type=sub_type,
                        months=months,
                        price=price,
                    ),
                    reply_markup=payment_confirm_kb(
                        months=months,
                        founder=founder,
                        transaction_id=transaction_info.id,
                        payment_url=transaction_info.payment_url,
                    ),
                )
                await state.set_state(SubscriptionStates.select_period)
            else:
                days = months  # для триала количество дней
                try:
                    await query.answer("Выбрал пробный период", show_alert=False)
                    await self.subscription_service.start_trial_subscription(
                        tg_id=query.from_user.id, days=days
                    )
                    await msg.delete()
                    await self.bot.send_message(
                        chat_id=query.from_user.id,
                        text=m_subscription.trial_period,
                        reply_markup=main_kb(active_subscription=True),
                    )
                    await state.clear()
                except APIClientError as e:
                    await query.answer(e.error.message, show_alert=True)

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
                device_limit=settings_bot.core.max_configs_per_user * 2,
                month=self.price_map.price_map_premium.get(1, 0),
                quarter=self.price_map.price_map_premium.get(3, 0),
                half_year=self.price_map.price_map_premium.get(6, 0),
                year=self.price_map.price_map_premium.get(12, 0),
            )
            if premium
            else m_subscription.start.format(
                device_limit=settings_bot.core.max_configs_per_user,
                month=self.price_map.price_map.get(1, 0),
                quarter=self.price_map.price_map.get(3, 0),
                half_year=self.price_map.price_map.get(6, 0),
                year=self.price_map.price_map.get(12, 0),
            )
        )

        await msg.edit_text(
            text=text,
            reply_markup=subscription_options_kb(
                premium=True if premium else False, trial=False
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
        user_logger = self.logger.bind(user=format_username(query.from_user))
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            await state.set_state(SubscriptionStates.wait_for_paid)
            months = callback_data.months
            founder = callback_data.founder
            transaction_id = callback_data.transaction_id
            if transaction_id is None:
                raise TransactionIdMissingError()
            premium = (await state.get_data()).get("premium", False)
            price_map = get_correct_price_map(premium=premium, founder=founder)
            price = price_map[months]
            sub_type = get_correct_sub_type(premium=premium, founder=founder)
            await self.subscription_service.payment_service.mark_payment_started(
                transaction_id=transaction_id
            )

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
                sub_type=sub_type,
            )
            await send_to_admins(
                bot=self.bot,
                message_text=admin_message,
                reply_markup=admin_payment_kb(
                    user_id=user.id,
                    months=months,
                    premium=premium if premium else False,
                    transaction_id=transaction_id,
                ),
                admin_mess_storage=self.redis_service,
                telegram_id=user.id,
            )

    @BaseRouter.log_method
    async def cancel_subscription(
        self, query: CallbackQuery, state: FSMContext, callback_data: SubscriptionCB
    ) -> None:
        """Обрабатывает отмену оформления подписки пользователем.

        Args:
            callback_data: Данные кнопки
            query (CallbackQuery): Callback от кнопки "Отмена".
            state (FSMContext): Контекст FSM.

        """
        msg = query.message
        if not msg:
            self.logger.warning("Сообщения нет, оно уже удалено")
            return
        if isinstance(msg, InaccessibleMessage):
            self.logger.warning("Сообщение уже старое его нельзя удалить")
            return
        user_logger = self.logger.bind(user=format_username(query.from_user))
        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            current_state = await state.get_state()
            await query.answer("Отменено ❌", show_alert=False)
            user_logger.info(f"Отмена подписки на шаге: {current_state}")
            # Если пользователь на втором шаге → вернуть к выбору периода
            if current_state == SubscriptionStates.select_period.state:
                transaction_id = callback_data.transaction_id
                if transaction_id is not None:
                    await self.subscription_service.cancel_transaction(
                        transaction_id=transaction_id
                    )
                # Восстанавливаем founder/premium/used_trial из состояния, а не
                # из дефолтов — иначе founder/premium при возврате назад видят
                # клавиатуру обычного пользователя (см. subscription_start).
                data = await state.get_data()
                premium = data.get("premium", False)
                founder = data.get("founder", False)
                used_trial = data.get("used_trial", False)
                await msg.edit_text(
                    text="Вы вернулись к выбору периода подписки ⏪",
                    reply_markup=subscription_options_kb(
                        premium=premium,
                        trial=True if founder else used_trial,
                        founder=founder,
                    ),
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
    @BaseRouter.require_message
    async def admin_confirm_payment(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
        callback_data: AdminPaymentCB,
    ) -> None:
        """Обрабатывает подтверждение оплаты администратором.

        Args:
            callback_data (AdminPaymentCB): Данные для формирования подписки.
            query (CallbackQuery): Callback от кнопки подтверждения админом.
            msg (Message): Сообщения от пользователя для редактирования.
            state (FSMContext): Контекст FSM.

        """
        user_logger = self.logger.bind(user=format_username(query.from_user))
        async with ChatActionSender.typing(
            bot=self.bot,
            chat_id=msg.chat.id,
        ):
            await query.answer("Админ подтвердил оплату", show_alert=False)
            user_id = callback_data.user_id
            months = callback_data.months
            premium = callback_data.premium
            transaction_id = callback_data.transaction_id
            confirm_transaction = await self.subscription_service.confirm_transaction(
                transaction_id
            )
            user_schema = confirm_transaction.subscription_res
            if (user_schema is None) or (user_schema.current_subscription is None):
                raise SubscriptionActivationFailedError(
                    tg_id=user_id, reason="подписка не найдена после оплаты"
                )
            if user_schema.current_subscription.type is None:
                raise SubscriptionActivationFailedError(
                    tg_id=user_id, reason="не указан тип подписки"
                )
            sub_type = user_schema.current_subscription.type.upper()
            user_logger.info(
                f"Админ подтвердил оплату пользователя {user_id} ({months} мес)"
            )
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=m_subscription.accept_paid.user.format(
                        months=months,
                        sub_type=sub_type,
                    ),
                    # reply_markup=main_kb(active_subscription=True),
                )
                referral_result: GrantReferralBonusResponse = (
                    confirm_transaction.referral_res
                )
                if referral_result.success and referral_result.inviter_telegram_id:
                    await self.bot.send_message(
                        chat_id=referral_result.inviter_telegram_id,
                        text=m_subscription.accept_paid.bonus.format(
                            user_info=f"@{user_schema.username}"
                        ),
                    )
            except TelegramBadRequest:
                await send_to_admins(
                    bot=self.bot,
                    message_text=m_subscription.accept_paid.error.format(
                        user_id=user_id
                    ),
                )
            try:
                ref_inf = referral_result.message
                await edit_admin_messages(
                    bot=self.bot,
                    user_id=user_id,
                    new_text=m_subscription.accept_paid.admin.format(
                        user_id=user_id,
                        sub_type=sub_type,
                        username=user_schema.username,
                        info=ref_inf,
                    ),
                    admin_mess_storage=self.redis_service,
                )
                await state.clear()
            except MessageNotFoundError as exc:
                user_logger.warning(str(exc))
                await self.bot.delete_message(
                    chat_id=msg.chat.id, message_id=msg.message_id
                )
                await send_to_admins(
                    bot=self.bot,
                    message_text=m_subscription.accept_paid.admin.format(
                        user_id=user_id,
                        premium=(
                            f"{ToggleSubscriptionMode.PREMIUM.upper()}"
                            if premium
                            else f"{ToggleSubscriptionMode.STANDARD.upper()}"
                        ),
                        username=user_schema.username,
                    ),
                )

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
        user_logger = self.logger.bind(user=format_username(query.from_user))
        async with ChatActionSender.typing(
            bot=self.bot,
            chat_id=msg.chat.id,
        ):
            await query.answer("Отклонено 🚫")
            await state.clear()
            user_id = callback_data.user_id
            months = callback_data.months
            transaction_id = callback_data.transaction_id
            await self.subscription_service.cancel_transaction(transaction_id)

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
                admin_mess_storage=self.redis_service,
            )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def check_subscription(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Проверка статуса подписки пользователя."""
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            info_text = (
                await self.subscription_service.get_subscription_and_referral_info(
                    tg_id=user.id
                )
            )

            await message.answer(
                text=m_subscription.check_subscription,
                reply_markup=ReplyKeyboardRemove(),
            )
            await self.bot.send_message(chat_id=user.id, text=info_text)
            await state.clear()
