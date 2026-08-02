from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import (
    MessageNotFoundError,
    PaymentLinkMissingError,
    SubscriptionActivationFailedError,
    TransactionIdMissingError,
    VPNConfigNotFoundError,
)
from bot.core.config import settings_bot
from bot.core.filters import IsAdmin
from bot.redis_service import RedisAdminMessageStorage, RedisPaymentMessageStorage
from bot.referrals.schemas import GrantReferralBonusResponse
from bot.referrals.services import ReferralService
from bot.subscription.enums import (
    TRIAL_PERIOD_SENTINEL,
    AdminPaymentAction,
    MySubscriptionAction,
    SubscriptionAction,
    ToggleSubscriptionMode,
)
from bot.subscription.keyboards.inline_kb import (
    AdminPaymentCB,
    MySubscriptionCB,
    SubscriptionCB,
    ToggleSubscriptionCB,
    admin_payment_kb,
    card_payment_kb,
    my_subscription_menu_kb,
    payment_method_kb,
    subscription_options_kb,
    transfer_payment_kb,
)
from bot.subscription.services import SubscriptionService
from bot.subscription.utils.sub_utils import get_correct_price_map, get_correct_sub_type
from bot.users.enums import MainMenuText
from bot.users.keyboards.markup_kb import main_kb
from bot.utils.base_router import BaseRouter
from bot.utils.formatting import format_subscription_end_date, format_username
from bot.utils.start_stop_bot import edit_admin_messages, send_to_admins
from bot.vpn.keyboards.inline_kb import (
    ConfigDeleteAction,
    ConfigDeleteCB,
    confirm_delete_config_kb,
    my_configs_kb,
)
from bot.vpn.services import VPNService
from shared.enums.admin_enum import FilterTypeEnum

m_subscription = settings_bot.messages.modes.subscription


class SubscriptionStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для процесса оформления подписки.

    Attributes
        subscription_start: Пользователь выбирает период/тариф подписки.
        select_payment_method: Транзакция создана, пользователь выбирает
            способ оплаты — картой (автоматически) или переводом (вручную).
        confirm_payment: Показан выбранный способ оплаты (ссылка на оплату
            картой либо реквизиты для перевода) — ждём отмену, "Я оплатил"
            (только перевод) или автоматическое подтверждение по вебхуку
            (только карта).
        wait_for_paid: Перевод отправлен, пользователь нажал "Я оплатил" —
            ждём проверки администратором.

    """

    subscription_start: State = State()
    select_payment_method: State = State()
    confirm_payment: State = State()
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
        vpn_service: VPNService,
        payment_mess_storage: RedisPaymentMessageStorage,
    ) -> None:
        super().__init__(bot, logger)
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self.redis_service = redis_service
        self.vpn_service = vpn_service
        self.payment_mess_storage = payment_mess_storage

    def _register_handlers(self) -> None:
        is_admin = IsAdmin()
        self.router.message.register(
            self.my_subscription_menu,
            or_f(
                F.text == MainMenuText.MY_SUBSCRIPTION.value,
                Command("subscription"),
            ),
        )
        self.router.message.register(
            self.get_subscription_menu,
            F.text == MainMenuText.GET_SUBSCRIPTION.value,
        )
        self.router.callback_query.register(
            self.renew_subscription_selected,
            MySubscriptionCB.filter(F.action == MySubscriptionAction.RENEW),
        )
        self.router.callback_query.register(
            self.config_delete_confirm,
            ConfigDeleteCB.filter(F.action == ConfigDeleteAction.CONFIRM),
        )
        self.router.callback_query.register(
            self.config_delete_execute,
            ConfigDeleteCB.filter(F.action == ConfigDeleteAction.EXECUTE),
        )
        self.router.callback_query.register(
            self.config_delete_cancel,
            ConfigDeleteCB.filter(F.action == ConfigDeleteAction.CANCEL),
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
            self.payment_method_selected,
            and_f(
                StateFilter(SubscriptionStates.select_payment_method),
                SubscriptionCB.filter(
                    F.action.in_(
                        {SubscriptionAction.PAY_CARD, SubscriptionAction.PAY_TRANSFER}
                    )
                ),
            ),
        )
        self.router.callback_query.register(
            self.user_paid,
            and_f(
                StateFilter(SubscriptionStates.confirm_payment),
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
                    StateFilter(SubscriptionStates.select_payment_method),
                    StateFilter(SubscriptionStates.confirm_payment),
                    StateFilter(SubscriptionStates.wait_for_paid),
                ),
                ~F.text.startswith("/"),
            ),
        )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def my_subscription_menu(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Показывает информацию о подписке, кнопки удаления конфигов и продления.

        Единая точка входа вместо трёх разрозненных кнопок в главном меню
        ("Выбрать"/"Продлить подписку" + "Проверить статус"); доступна и по
        кнопке меню, и по команде /subscription — независимо от /start.

        Args:
            message (Message): Сообщение пользователя.
            user (TgUser): Пользователь Телеграм из сообщения.
            state (FSMContext): Контекст FSM для управления состояниями.

        """
        await state.clear()
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            info_text, keyboard = await self._build_my_subscription_view(user.id)
            await message.answer(text=info_text, reply_markup=keyboard)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def get_subscription_menu(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Сразу открывает выбор тарифа — для пользователей без активной подписки.

        В отличие от `my_subscription_menu`, не показывает промежуточный экран
        "Моя подписка" с дополнительной кнопкой: кнопка "Оформить подписку"
        в главном меню обещает переход к оформлению, а не к статусу.

        Args:
            message (Message): Сообщение пользователя.
            user (TgUser): Пользователь Телеграм из сообщения.
            state (FSMContext): Контекст FSM для управления состояниями.

        """
        await self._show_subscription_options(
            chat_id=message.chat.id, user=user, state=state
        )

    async def _build_my_subscription_view(
        self, tg_id: int
    ) -> tuple[str, InlineKeyboardMarkup]:
        """Собирает текст и клавиатуру экрана "Моя подписка".

        Клавиатура — это кнопки удаления по одной на каждый VPN-конфиг
        пользователя плюс кнопка "Оформить/продлить подписку".

        Args:
            tg_id (int): Telegram ID пользователя.

        Returns
            tuple[str, InlineKeyboardMarkup]: Текст сообщения и клавиатура.

        """
        info_text = await self.subscription_service.get_subscription_and_referral_info(
            tg_id=tg_id
        )
        configs = await self.subscription_service.get_user_vpn_configs(tg_id=tg_id)
        configs_kb = my_configs_kb(configs)
        renew_kb = my_subscription_menu_kb()
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[*configs_kb.inline_keyboard, *renew_kb.inline_keyboard]
        )
        return info_text, keyboard

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def config_delete_confirm(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ConfigDeleteCB,
    ) -> None:
        """Запрашивает подтверждение удаления выбранного пользователем конфига.

        Args:
            query (CallbackQuery): Callback от кнопки конфига в списке.
            msg (Message): Сообщение экрана "Моя подписка" для редактирования.
            callback_data (ConfigDeleteCB): Данные кнопки (id конфига).

        """
        await query.answer()
        configs = await self.subscription_service.get_user_vpn_configs(
            tg_id=query.from_user.id
        )
        config = next((c for c in configs if c.id == callback_data.config_id), None)
        if config is None:
            raise VPNConfigNotFoundError(config_id=callback_data.config_id)

        await msg.edit_text(
            text=m_subscription.config_delete.confirm.format(
                file_name=config.file_name
            ),
            reply_markup=confirm_delete_config_kb(config_id=config.id),
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def config_delete_execute(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ConfigDeleteCB,
    ) -> None:
        """Удаляет подтверждённый пользователем конфиг и обновляет экран.

        Args:
            query (CallbackQuery): Callback от кнопки подтверждения удаления.
            msg (Message): Сообщение с подтверждением для редактирования.
            callback_data (ConfigDeleteCB): Данные кнопки (id конфига).

        """
        await query.answer(m_subscription.config_delete.deleting)
        tg_id = query.from_user.id
        configs = await self.subscription_service.get_user_vpn_configs(tg_id=tg_id)
        config = next((c for c in configs if c.id == callback_data.config_id), None)
        if config is None:
            raise VPNConfigNotFoundError(config_id=callback_data.config_id)

        self.logger.bind(user=format_username(query.from_user)).info(
            f"Пользователь удаляет свой конфиг {config.file_name}"
        )
        await self.vpn_service.delete_user_config(tg_id=tg_id, config=config)

        info_text, keyboard = await self._build_my_subscription_view(tg_id)
        success_text = m_subscription.config_delete.success.format(
            file_name=config.file_name
        )
        await msg.edit_text(
            text=f"{success_text}\n\n{info_text}",
            reply_markup=keyboard,
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def config_delete_cancel(
        self,
        query: CallbackQuery,
        msg: Message,
    ) -> None:
        """Отменяет удаление конфига и возвращает экран "Моя подписка" без изменений.

        Args:
            query (CallbackQuery): Callback от кнопки "Отмена".
            msg (Message): Сообщение с подтверждением для редактирования.

        """
        await query.answer(m_subscription.config_delete.cancelled)
        info_text, keyboard = await self._build_my_subscription_view(query.from_user.id)
        await msg.edit_text(text=info_text, reply_markup=keyboard)

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def renew_subscription_selected(
        self, query: CallbackQuery, msg: Message, state: FSMContext
    ) -> None:
        """Обрабатывает выбор "Оформить/продлить подписку" в подменю "Моя подписка".

        Args:
            query (CallbackQuery): Callback от кнопки подменю.
            msg (Message): Сообщение подменю, которое будет удалено.
            state (FSMContext): Контекст FSM.

        """
        await query.answer()
        await msg.delete()
        await self._show_subscription_options(
            chat_id=msg.chat.id, user=query.from_user, state=state
        )

    async def _show_subscription_options(
        self, chat_id: int, user: TgUser, state: FSMContext
    ) -> None:
        """Отправляет варианты подписки/тарифов, подходящие текущему пользователю.

        Args:
            chat_id (int): Telegram chat_id, куда отправлять сообщения.
            user (TgUser): Пользователь Телеграм, оформляющий подписку.
            state (FSMContext): Контекст FSM для управления состояниями.

        """
        user_logger = self.logger.bind(user=format_username(user))
        user_logger.info("Начало оформления подписки")
        async with ChatActionSender.typing(bot=self.bot, chat_id=chat_id):
            (
                is_premium,
                role,
                is_active_sbscr,
                used_trial,
            ) = await self.subscription_service.check_premium(tg_id=user.id)
            await self.bot.send_message(
                chat_id=chat_id,
                text="Начнем оформление подписки",
                reply_markup=ReplyKeyboardRemove(),
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
                # Founder-статус даёт доступ выше пробного периода, поэтому кнопка
                # триала скрывается — trial=True значит здесь "уже использован".
                kb = subscription_options_kb(premium=False, trial=True, founder=True)
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
            await state.update_data(
                premium=is_premium, founder=founder, used_trial=used_trial
            )
            await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
            await state.set_state(SubscriptionStates.subscription_start)

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
            if months != TRIAL_PERIOD_SENTINEL:
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

                await state.update_data(payment_url=transaction_info.payment_url)

                await msg.edit_text(
                    text=m_subscription.choose_payment_method.format(
                        sub_type=sub_type,
                        months=months,
                        price=price,
                    ),
                    reply_markup=payment_method_kb(
                        months=months,
                        founder=founder,
                        transaction_id=transaction_info.id,
                        has_card_option=bool(transaction_info.payment_url),
                    ),
                )
                await state.set_state(SubscriptionStates.select_payment_method)
            else:
                try:
                    await self.subscription_service.start_trial_subscription(
                        tg_id=query.from_user.id, days=TRIAL_PERIOD_SENTINEL
                    )
                except APIClientError as e:
                    user_logger.warning(
                        f"Не удалось активировать пробный период: {e.error.message}"
                    )
                    await query.answer(e.error.message, show_alert=True)
                    await send_to_admins(
                        bot=self.bot,
                        message_text=(
                            f"⚠️ Пользователь {format_username(query.from_user)} "
                            f"({query.from_user.id}) не смог активировать пробный "
                            f"период: {e.error.message}"
                        ),
                    )
                else:
                    await query.answer("Выбрал пробный период", show_alert=False)
                    await msg.delete()
                    await self.bot.send_message(
                        chat_id=query.from_user.id,
                        text=m_subscription.trial_period,
                        reply_markup=main_kb(active_subscription=True),
                    )
                    await state.clear()

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def payment_method_selected(
        self,
        query: CallbackQuery,
        msg: Message,
        state: FSMContext,
        callback_data: SubscriptionCB,
    ) -> None:
        """Обрабатывает выбор способа оплаты — картой или переводом.

        Картой: показывает ссылку на оплату через платёжный шлюз, подтверждение
        подписки происходит автоматически по вебхуку — кнопки "Я оплатил" тут нет.

        Переводом: показывает реквизиты для перевода и кнопку "Я оплатил",
        по нажатию на которую администратор получает уведомление и подтверждает
        оплату вручную (см. `user_paid`, `admin_confirm_payment`).

        Args:
            query (CallbackQuery): Callback от кнопки выбора способа оплаты.
            msg (Message): Сообщение с выбором способа оплаты для редактирования.
            state (FSMContext): Контекст FSM.
            callback_data (SubscriptionCB): Данные кнопки (способ оплаты, транзакция).

        """
        months = callback_data.months
        founder = callback_data.founder
        transaction_id = callback_data.transaction_id
        if transaction_id is None:
            raise TransactionIdMissingError()

        data = await state.get_data()
        is_premium = data.get("premium", False)
        price_map = get_correct_price_map(premium=is_premium, founder=founder)
        sub_type = get_correct_sub_type(premium=is_premium, founder=founder)
        price = price_map[months]

        async with ChatActionSender.typing(bot=self.bot, chat_id=msg.chat.id):
            if callback_data.action == SubscriptionAction.PAY_CARD:
                payment_url = data.get("payment_url")
                if not payment_url:
                    raise PaymentLinkMissingError(transaction_id)
                await query.answer("Оплата картой", show_alert=False)
                await msg.edit_text(
                    text=m_subscription.pay_by_card,
                    reply_markup=card_payment_kb(payment_url=payment_url),
                )
                # Запоминаем это сообщение, чтобы по итогам вебхука
                # платёжного шлюза отредактировать именно его — заменить
                # устаревшую ссылку на оплату итоговым статусом, а не
                # оставлять пользователю неактуальный экран.
                await self.payment_mess_storage.save(
                    transaction_id=transaction_id,
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                )
            else:  # SubscriptionAction.PAY_TRANSFER
                await query.answer("Оплата переводом", show_alert=False)
                await msg.edit_text(
                    text=m_subscription.select_period.format(
                        sub_type=sub_type,
                        months=months,
                        price=price,
                    ),
                    reply_markup=transfer_payment_kb(
                        months=months,
                        founder=founder,
                        transaction_id=transaction_id,
                    ),
                )
            await state.set_state(SubscriptionStates.confirm_payment)

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
            await self.subscription_service.mark_payment_started(
                transaction_id=transaction_id
            )

            user_logger.info(
                f"Пользователь нажал оплату ({months} мес, {price}₽), "
                f"transaction_id={transaction_id}"
            )
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
            back_to_period_states = {
                SubscriptionStates.select_payment_method.state,
                SubscriptionStates.confirm_payment.state,
            }
            if current_state in back_to_period_states:
                transaction_id = callback_data.transaction_id
                if transaction_id is not None:
                    await self.subscription_service.cancel_transaction(
                        transaction_id=transaction_id
                    )
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
                f"Админ подтвердил оплату пользователя {user_id} ({months} мес), "
                f"transaction_id={transaction_id}"
            )
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=m_subscription.accept_paid.user.format(
                        months=months,
                        sub_type=sub_type,
                        amount=confirm_transaction.transaction_res.amount,
                        end_date=format_subscription_end_date(
                            user_schema.current_subscription.end_date
                        ),
                    ),
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
                f"Админ отклонил оплату пользователя {user_id} ({months} мес), "
                f"transaction_id={transaction_id}"
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
