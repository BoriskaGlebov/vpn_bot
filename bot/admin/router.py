from __future__ import annotations

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from aiogram.types import CallbackQuery
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.keyboards.inline_kb import (
    AdminCB,
    UserPageCB,
)
from bot.admin.services import AdminService
from bot.database import connection
from bot.utils.base_router import BaseRouter


class AdminStates(StatesGroup):  # type: ignore[misc]
    pass


class AdminRouter(BaseRouter):
    """Роутер для обработки действий администратора."""

    def __init__(self, bot: Bot, logger: Logger, admin_service: AdminService) -> None:
        super().__init__(bot, logger)
        self.admin_service = admin_service

    def _register_handlers(self) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def admin_action_callback(
        self,
        query: CallbackQuery,
        state: FSMContext,
        session: AsyncSession,
        callback_data: UserPageCB,
    ) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def role_select_callback(
        self,
        query: CallbackQuery,
        callback_data: UserPageCB,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def sub_select_callback(
        self,
        query: CallbackQuery,
        session: AsyncSession,
        callback_data: UserPageCB,
        state: FSMContext,
    ) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def cansel_callback(
        self,
        query: CallbackQuery,
        session: AsyncSession,
        callback_data: UserPageCB,
    ) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def show_filtered_users(
        self,
        query: CallbackQuery,
        callback_data: AdminCB,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        pass

    @connection()
    @BaseRouter.log_method
    async def user_page_callback(
        self, query: CallbackQuery, callback_data: UserPageCB, session: AsyncSession
    ) -> None:
        pass
