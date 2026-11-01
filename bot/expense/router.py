from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any

from aiogram import Bot, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
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

m_expense = settings_bot.messages.modes.expense


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
            ~F.text.startswith("/"),
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
            ~F.text.startswith("/"),
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
            ~F.text.startswith("/"),
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

    async def _edit_dialog(
        self,
        chat_id: int,
        dialog_msg_id: int | None,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        fallback_message: Message | None = None,
    ) -> None:
        """Редактирует карточку диалога или создаёт новое сообщение как fallback.

        Args:
            chat_id: ID чата.
            dialog_msg_id: ID сообщения-карточки диалога.
            text: Новый текст карточки.
            reply_markup: Новая клавиатура (опционально).
            fallback_message: Сообщение для fallback-ответа, если карточка недоступна.

        """
        if dialog_msg_id:
            await self.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=dialog_msg_id,
                reply_markup=reply_markup,
            )
        elif fallback_message:
            await fallback_message.answer(text=text, reply_markup=reply_markup)

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
            text = m_expense.menu.format(
                year=summary.year,
                revenue=f"{summary.total_revenue:,}".replace(",", " "),
                expenses=f"{summary.total_expenses:,}".replace(",", " "),
                profit=f"{summary.total_profit:,}".replace(",", " "),
            )
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
        await state.update_data(dialog_msg_id=msg.message_id)
        await msg.edit_text(m_expense.select_category, reply_markup=category_kb())

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
        label = CATEGORY_LABELS.get(
            callback_data.category, callback_data.category.value
        )
        await state.update_data(
            category=callback_data.category.value, category_label=label
        )
        await query.answer(m_expense.category_answer.format(label=label))
        await state.set_state(ExpenseStates.enter_amount)
        await msg.edit_text(m_expense.enter_amount.format(label=label))

    @BaseRouter.log_method
    async def amount_entered(self, message: Message, state: FSMContext) -> None:
        """Валидирует сумму, спрашивает описание.

        Args:
            message: Входящее сообщение с суммой.
            state: Контекст FSM.

        """
        text = (message.text or "").strip()
        data = await state.get_data()
        dialog_msg_id: int | None = data.get("dialog_msg_id")
        chat_id = message.chat.id
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.delete()
            label = data.get("category_label", "")
            await self._edit_dialog(
                chat_id=chat_id,
                dialog_msg_id=dialog_msg_id,
                text=m_expense.amount_invalid
                + "\n\n"
                + m_expense.enter_amount.format(label=label),
                fallback_message=message,
            )
            return
        await message.delete()
        await state.update_data(amount=amount)
        await state.set_state(ExpenseStates.enter_description)
        await self._edit_dialog(
            chat_id=chat_id,
            dialog_msg_id=dialog_msg_id,
            text=m_expense.enter_description.format(
                amount=f"{amount:,}".replace(",", " ")
            ),
            reply_markup=skip_kb(),
            fallback_message=message,
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
        await msg.edit_text(m_expense.select_period, reply_markup=period_kb())

    @BaseRouter.log_method
    async def description_entered(self, message: Message, state: FSMContext) -> None:
        """Сохраняет описание, переходит к выбору периода.

        Args:
            message: Входящее сообщение с описанием.
            state: Контекст FSM.

        """
        desc = (message.text or "").strip()
        data = await state.get_data()
        dialog_msg_id: int | None = data.get("dialog_msg_id")
        chat_id = message.chat.id
        await message.delete()
        await state.update_data(description=desc if desc else None)
        await state.set_state(ExpenseStates.select_period)
        await self._edit_dialog(
            chat_id=chat_id,
            dialog_msg_id=dialog_msg_id,
            text=m_expense.select_period,
            reply_markup=period_kb(),
            fallback_message=message,
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
            m_expense.select_node.format(
                period_start=f"{period_start:%Y-%m-%d}",
                period_end=f"{period_end:%Y-%m-%d}",
            ),
            reply_markup=node_kb(),
        )

    @BaseRouter.log_method
    async def period_entered(self, message: Message, state: FSMContext) -> None:
        """Парсит дату из текста, переходит к ноде.

        Args:
            message: Входящее сообщение с датой в формате YYYY-MM-DD.
            state: Контекст FSM.

        """
        text_input = (message.text or "").strip()
        data = await state.get_data()
        dialog_msg_id: int | None = data.get("dialog_msg_id")
        chat_id = message.chat.id
        try:
            period_start = date.fromisoformat(text_input)
        except ValueError:
            await message.delete()
            await self._edit_dialog(
                chat_id=chat_id,
                dialog_msg_id=dialog_msg_id,
                text=m_expense.date_invalid + "\n\n" + m_expense.select_period,
                reply_markup=period_kb(),
                fallback_message=message,
            )
            return
        last_day = calendar.monthrange(period_start.year, period_start.month)[1]
        period_end = date(period_start.year, period_start.month, last_day)
        await message.delete()
        await state.update_data(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
        )
        await state.set_state(ExpenseStates.select_node)
        await self._edit_dialog(
            chat_id=chat_id,
            dialog_msg_id=dialog_msg_id,
            text=m_expense.select_node.format(
                period_start=f"{period_start:%Y-%m-%d}",
                period_end=f"{period_end:%Y-%m-%d}",
            ),
            reply_markup=node_kb(),
            fallback_message=message,
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
        text = m_expense.confirm.format(
            category=cat_label,
            amount=f"{data['amount']:,}".replace(",", " "),
            description=data.get("description") or "—",
            period_start=data["period_start"],
            period_end=data.get("period_end", "—"),
            node=node or "—",
        )
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
                m_expense.added.format(
                    amount=f"{result.amount:,}".replace(",", " "),
                    category=cat_label,
                    node=result.node_name or "—",
                    period=f"{result.period_start:%Y-%m}",
                )
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
        await query.answer(m_expense.cancelled_toast)
        await msg.edit_text(m_expense.cancelled)
