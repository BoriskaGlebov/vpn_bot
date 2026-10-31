from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any

from aiogram import Bot, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.core.config import settings_bot
from bot.core.filters import IsAdmin
from bot.expense.keyboards.inline_kb import (
    CATEGORY_LABELS,
    ExpenseAction,
    ExpenseCategoryCB,
    ExpenseCB,
    ExpenseNodeCB,
    category_kb,
    confirm_kb,
    expense_menu_kb,
    node_kb,
    period_kb,
    skip_kb,
)
from bot.expense.schemas import SExpenseCreate
from bot.expense.services import ExpenseService
from bot.utils.base_router import BaseRouter
from shared.enums.expense_enum import ExpenseCategory


class ExpenseStates(StatesGroup):  # type: ignore[misc]
    """FSM-состояния для ввода расхода."""

    select_category: State = State()
    enter_amount: State = State()
    enter_description: State = State()
    select_period: State = State()
    select_node: State = State()
    confirm: State = State()


class ExpenseRouter(BaseRouter):
    """Роутер для ввода расходов через Telegram."""

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        expense_service: ExpenseService,
    ) -> None:
        """Инициализирует роутер расходов.

        Args:
            bot: Экземпляр бота Telegram.
            logger: Экземпляр логгера loguru.
            expense_service: Сервис управления расходами.

        """
        self.expense_service = expense_service
        super().__init__(bot, logger)

    def _register_handlers(self) -> None:
        is_admin = IsAdmin()

        self.router.callback_query.register(
            self.expense_menu,
            ExpenseCB.filter(F.action == ExpenseAction.MENU),
            is_admin,
        )
        self.router.callback_query.register(
            self.start_add_expense,
            ExpenseCB.filter(F.action == ExpenseAction.ADD),
            is_admin,
        )
        self.router.callback_query.register(
            self.category_selected,
            ExpenseCategoryCB.filter(),
            StateFilter(ExpenseStates.select_category),
            is_admin,
        )
        self.router.message.register(
            self.amount_entered,
            StateFilter(ExpenseStates.enter_amount),
            is_admin,
        )
        self.router.callback_query.register(
            self.skip_description,
            ExpenseCB.filter(F.action == ExpenseAction.SKIP),
            StateFilter(ExpenseStates.enter_description),
            is_admin,
        )
        self.router.message.register(
            self.description_entered,
            StateFilter(ExpenseStates.enter_description),
            is_admin,
        )
        self.router.callback_query.register(
            self.use_current_period,
            ExpenseCB.filter(F.action == ExpenseAction.USE_CURRENT_PERIOD),
            StateFilter(ExpenseStates.select_period),
            is_admin,
        )
        self.router.message.register(
            self.period_entered,
            StateFilter(ExpenseStates.select_period),
            is_admin,
        )
        self.router.callback_query.register(
            self.node_selected,
            ExpenseNodeCB.filter(),
            StateFilter(ExpenseStates.select_node),
            is_admin,
        )
        self.router.callback_query.register(
            self.confirm_expense,
            ExpenseCB.filter(F.action == ExpenseAction.CONFIRM),
            StateFilter(ExpenseStates.confirm),
            is_admin,
        )
        self.router.callback_query.register(
            self.cancel_expense,
            ExpenseCB.filter(F.action == ExpenseAction.CANCEL),
            is_admin,
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def expense_menu(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCB,
    ) -> None:
        """Показывает меню расходов с балансом за год.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            summary = await self.expense_service.get_yearly_summary()
            text = (
                f"📊 <b>Финансы за {summary.year} год</b>\n\n"
                f"💰 Доход: <b>{summary.total_revenue:,}</b> ₽\n"
                f"📉 Расходы: <b>{summary.total_expenses:,}</b> ₽\n"
                f"📈 Прибыль: <b>{summary.total_profit:,}</b> ₽"
            ).replace(",", " ")
            await msg.edit_text(text=text, reply_markup=expense_menu_kb())

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def start_add_expense(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCB,
        state: FSMContext,
    ) -> None:
        """Начинает flow ввода расхода: спрашивает категорию.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback.
            state: Контекст FSM.

        """
        await state.set_state(ExpenseStates.select_category)
        await msg.edit_text(
            "Выберите категорию расхода:",
            reply_markup=category_kb(),
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def category_selected(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCategoryCB,
        state: FSMContext,
    ) -> None:
        """Сохраняет категорию, спрашивает сумму.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback с категорией.
            state: Контекст FSM.

        """
        await state.update_data(category=callback_data.category.value)
        label = CATEGORY_LABELS.get(
            callback_data.category, callback_data.category.value
        )
        await query.answer(f"Категория: {label}")
        await state.set_state(ExpenseStates.enter_amount)
        await msg.edit_text(
            f"Категория: {label}\n\nВведите сумму расхода в рублях (целое число):"
        )

    @BaseRouter.log_method
    async def amount_entered(self, message: Message, state: FSMContext) -> None:
        """Валидирует сумму, спрашивает описание.

        Args:
            message: Входящее сообщение с суммой.
            state: Контекст FSM.

        """
        text = (message.text or "").strip()
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                "⚠️ Введите целое положительное число (сумму в рублях)."
            )
            return
        await state.update_data(amount=amount)
        await state.set_state(ExpenseStates.enter_description)
        await message.answer(
            f"Сумма: <b>{amount:,}</b> ₽\n\n"
            "Введите описание расхода или нажмите «Пропустить»:".replace(",", " "),
            reply_markup=skip_kb(),
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def skip_description(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCB,
        state: FSMContext,
    ) -> None:
        """Пропускает описание, переходит к выбору периода.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback.
            state: Контекст FSM.

        """
        await state.update_data(description=None)
        await state.set_state(ExpenseStates.select_period)
        await msg.edit_text(
            "Выберите период расхода.\n"
            "Нажмите «Текущий месяц» или введите дату в формате <b>YYYY-MM-DD</b>:",
            reply_markup=period_kb(),
        )

    @BaseRouter.log_method
    async def description_entered(self, message: Message, state: FSMContext) -> None:
        """Сохраняет описание, переходит к выбору периода.

        Args:
            message: Входящее сообщение с описанием.
            state: Контекст FSM.

        """
        desc = (message.text or "").strip()
        await state.update_data(description=desc if desc else None)
        await state.set_state(ExpenseStates.select_period)
        await message.answer(
            "Выберите период расхода.\n"
            "Нажмите «Текущий месяц» или введите дату в формате <b>YYYY-MM-DD</b>:",
            reply_markup=period_kb(),
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def use_current_period(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCB,
        state: FSMContext,
    ) -> None:
        """Устанавливает период = 1-е число текущего месяца, переходит к ноде.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback.
            state: Контекст FSM.

        """
        tz = settings_bot.core.tzinfo
        now = datetime.now(tz=tz)
        period_start = date(now.year, now.month, 1)
        last_day = calendar.monthrange(now.year, now.month)[1]
        period_end = date(now.year, now.month, last_day)
        await state.update_data(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
        )
        await state.set_state(ExpenseStates.select_node)
        await msg.edit_text(
            f"Период: {period_start:%Y-%m-%d} — {period_end:%Y-%m-%d}\n\n"
            "Выберите VPN-ноду или «Без привязки»:",
            reply_markup=node_kb(),
        )

    @BaseRouter.log_method
    async def period_entered(self, message: Message, state: FSMContext) -> None:
        """Парсит дату из текста, переходит к ноде.

        Args:
            message: Входящее сообщение с датой в формате YYYY-MM-DD.
            state: Контекст FSM.

        """
        text = (message.text or "").strip()
        try:
            period_start = date.fromisoformat(text)
        except ValueError:
            await message.answer(
                "⚠️ Некорректная дата. Введите в формате <b>YYYY-MM-DD</b> (например, 2026-10-01)."
            )
            return
        last_day = calendar.monthrange(period_start.year, period_start.month)[1]
        period_end = date(period_start.year, period_start.month, last_day)
        await state.update_data(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
        )
        await state.set_state(ExpenseStates.select_node)
        await message.answer(
            f"Период: {period_start:%Y-%m-%d} — {period_end:%Y-%m-%d}\n\n"
            "Выберите VPN-ноду или «Без привязки»:",
            reply_markup=node_kb(),
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def node_selected(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseNodeCB,
        state: FSMContext,
    ) -> None:
        """Сохраняет ноду, показывает подтверждение.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback с именем ноды.
            state: Контекст FSM.

        """
        node = callback_data.node_name or None
        await state.update_data(node_name=node)
        data: dict[str, Any] = await state.get_data()

        cat_enum = ExpenseCategory(data["category"])
        cat_label = CATEGORY_LABELS.get(cat_enum, data["category"])
        text = (
            "📋 <b>Подтвердите расход:</b>\n\n"
            f"📂 Категория: {cat_label}\n"
            f"💵 Сумма: <b>{data['amount']:,}</b> ₽\n"
            f"📝 Описание: {data.get('description') or '—'}\n"
            f"📅 Период: {data['period_start']} — {data.get('period_end', '—')}\n"
            f"🖥 Нода: {node or '—'}"
        ).replace(",", " ")
        await state.set_state(ExpenseStates.confirm)
        await msg.edit_text(text=text, reply_markup=confirm_kb())

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def confirm_expense(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCB,
        state: FSMContext,
    ) -> None:
        """Отправляет расход в API и показывает результат.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback.
            state: Контекст FSM.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            data: dict[str, Any] = await state.get_data()
            payload = SExpenseCreate(
                amount=data["amount"],
                category=ExpenseCategory(data["category"]),
                description=data.get("description"),
                period_start=date.fromisoformat(data["period_start"]),
                period_end=(
                    date.fromisoformat(data["period_end"])
                    if data.get("period_end")
                    else None
                ),
                node_name=data.get("node_name"),
            )
            result = await self.expense_service.create_expense(payload)

            cat_label = CATEGORY_LABELS.get(result.category, result.category.value)
            await state.clear()
            await msg.edit_text(
                f"✅ Расход добавлен: {result.amount:,} ₽ / "
                f"{cat_label} / {result.node_name or '—'} / "
                f"{result.period_start:%Y-%m}".replace(",", " ")
            )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def cancel_expense(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: ExpenseCB,
        state: FSMContext,
    ) -> None:
        """Отменяет ввод расхода.

        Args:
            query: Входящий callback-запрос.
            msg: Сообщение для редактирования.
            callback_data: Данные callback.
            state: Контекст FSM.

        """
        await state.clear()
        await query.answer("Отменено")
        await msg.edit_text("❌ Ввод расхода отменён.")
