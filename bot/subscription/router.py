from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.subscription.keyboards.inline_kb import (
    AdminPaymentCB,
    SubscriptionCB,
    ToggleSubscriptionCB,
)
from bot.subscription.services import SubscriptionService
from bot.utils.base_router import BaseRouter

m_subscription = settings_bot.messages["modes"]["subscription"]


class SubscriptionStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для процесса оформления подписки."""

    pass


class SubscriptionRouter(BaseRouter):
    """Роутер для управления процессом подписки пользователей."""

    def __init__(
        self, bot: Bot, logger: Logger, subscription_service: SubscriptionService
    ) -> None:
        super().__init__(bot, logger)
        self.subscription_service = subscription_service

    def _register_handlers(self) -> None:
        pass

    @BaseRouter.log_method
    @connection()
    async def start_subscription(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        pass

    @BaseRouter.log_method
    @connection()
    async def subscription_selected(
        self,
        query: CallbackQuery,
        state: FSMContext,
        session: AsyncSession,
        callback_data: SubscriptionCB,
    ) -> None:
        pass

    @BaseRouter.log_method
    async def toggle_subscription_mode(
        self,
        query: CallbackQuery,
        state: FSMContext,
        callback_data: ToggleSubscriptionCB,
    ) -> None:
        pass

    @BaseRouter.log_method
    async def user_paid(
        self, query: CallbackQuery, state: FSMContext, callback_data: SubscriptionCB
    ) -> None:
        pass

    @BaseRouter.log_method
    async def cancel_subscription(
        self, query: CallbackQuery, state: FSMContext
    ) -> None:
        pass

    @BaseRouter.log_method
    @connection()
    async def admin_confirm_payment(
        self,
        query: CallbackQuery,
        session: AsyncSession,
        state: FSMContext,
        callback_data: AdminPaymentCB,
    ) -> None:
        pass

    @BaseRouter.log_method
    async def admin_decline_payment(
        self, query: CallbackQuery, state: FSMContext, callback_data: AdminPaymentCB
    ) -> None:
        pass
