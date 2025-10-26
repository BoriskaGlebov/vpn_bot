from __future__ import annotations

import datetime

from aiogram import Bot, F
from aiogram.filters import StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.admin.keyboards.inline_kb import (
    AdminCB,
    UserPageCB,
    admin_user_control_kb,
    role_selection_kb,
    subscription_selection_kb,
    user_navigation_kb,
)
from bot.database import connection
from bot.users.dao import RoleDAO, UserDAO
from bot.users.models import Role, User, UserRole
from bot.users.router import m_admin
from bot.users.schemas import SRole, SUserTelegramID
from bot.utils.base_router import BaseRouter


class AdminStates(StatesGroup):  # type: ignore[misc]
    """Состояния администратора при управлении пользователями."""

    select_role: State = State()
    select_period: State = State()


class AdminRouter(BaseRouter):
    """Роутер для обработки действий администратора."""

    def __init__(self, bot: Bot, logger: Logger) -> None:
        super().__init__(bot, logger)

    def _register_handlers(self) -> None:
        self.router.callback_query.register(
            self.admin_action_callback,
            or_f(
                UserPageCB.filter(F.action == "role_change"),
                UserPageCB.filter(F.action == "sub_manage"),
            ),
        )
        self.router.callback_query.register(
            self.role_select_callback,
            and_f(
                StateFilter(AdminStates.select_role),
                UserPageCB.filter(F.action == "role_select"),
            ),
        )
        self.router.callback_query.register(
            self.sub_select_callback,
            and_f(
                StateFilter(AdminStates.select_period),
                UserPageCB.filter(F.action == "sub_select"),
            ),
        )
        self.router.callback_query.register(
            self.cansel_callback,
            or_f(
                UserPageCB.filter(F.action == "role_cancel"),
                UserPageCB.filter(F.action == "subscr_cancel"),
            ),
        )
        self.router.callback_query.register(
            self.show_filtered_users,
            AdminCB.filter(),
        )
        self.router.callback_query.register(
            self.user_page_callback,
            UserPageCB.filter(F.action == "navigate"),
        )

    @staticmethod
    async def _get_users_by_filter(
        session: AsyncSession, filter_type: str
    ) -> list[User]:
        """Вспомогательная функция: получить пользователей по фильтру."""
        stmt = (
            select(User)
            .join(User.user_roles)
            .join(UserRole.role)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
        )
        if filter_type != "all":
            stmt = stmt.where(Role.name == filter_type)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _format_user_text(user: User, key: str = "user") -> str:
        """Форматирует текст пользователя для сообщения."""
        template: str = m_admin[key]
        return template.format(
            first_name=user.first_name or "-",
            last_name=user.last_name or "-",
            username=user.username or "-",
            telegram_id=user.telegram_id or "-",
            roles=",".join([str(role) for role in user.roles]) if user.roles else "-",
            subscription=user.subscription or "-",
        )

    @connection()
    @BaseRouter.log_method
    async def admin_action_callback(
        self,
        query: CallbackQuery,
        state: FSMContext,
        session: AsyncSession,
        callback_data: UserPageCB,
    ) -> None:
        """Обрабатывает действия администратора при редактировании пользователя.

        В зависимости от действия (`role_change` или `sub_manage`),
        переводит администратора в соответствующее состояние
        и предлагает выбрать новую роль или срок подписки.

        Args:
            query (CallbackQuery): Объект колбэка.
            state (FSMContext): Контекст состояний FSM.
            session (AsyncSession): Сессия базы данных.
            callback_data (UserPageCB | None): Данные из callback кнопки.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await query.answer("Отработал")
            user_id: int | None = callback_data.telegram_id
            if user_id is None:
                raise ValueError("Необходимо передать в запрос telegram_id")
            user_schema = SUserTelegramID(telegram_id=user_id)
            user = await UserDAO.find_one_or_none(session=session, filters=user_schema)
            if user is None:
                raise ValueError(
                    f"Не нашел пользователя с указанным telegram_id {user_id}"
                )
            old_text = await self._format_user_text(user, "edit_user")
            if callback_data.action == "role_change":
                await state.set_state(AdminStates.select_role)
                await query.message.edit_text(
                    f"{old_text}\n {'*' * 20}\nВыберите новую роль для пользователя:",
                    reply_markup=role_selection_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )
            elif callback_data.action == "sub_manage":
                await state.set_state(AdminStates.select_period)
                await query.message.edit_text(
                    f"{old_text}\n{'*' * 20}\nВыберите срок подписки для пользователя:",
                    reply_markup=subscription_selection_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )

    @connection()
    @BaseRouter.log_method
    async def role_select_callback(
        self,
        query: CallbackQuery,
        callback_data: UserPageCB,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        """Изменяет роль пользователя.

        Args:
            query (CallbackQuery): Объект колбэка.
            callback_data (UserPageCB): Данные из callback кнопки.
            session (AsyncSession): Сессия базы данных.
            state (FSMContext): Контекст состояний FSM.

        Raises
            ValueError: Если пользователь или роль не найдены.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await state.clear()
            role_name = callback_data.filter_type
            user_id = callback_data.telegram_id
            if user_id is None:
                raise ValueError("Необходимо передать в запрос telegram_id")
            user_schema = SUserTelegramID(telegram_id=int(user_id))
            user = await UserDAO.find_one_or_none(session=session, filters=user_schema)
            user_id = int(user_id)
            role_schema = SRole(name=role_name)
            role = await RoleDAO.find_one_or_none(session, filters=role_schema)
            if user is None or role is None:
                raise ValueError(
                    f"Не нашел такого пользователя/роль ({user_id}/{role_name})"
                )
            user.roles = [role]
            if role.name == "founder":
                if datetime.datetime.now().year == 2025:
                    current_date = datetime.datetime.now(tz=datetime.UTC)
                    new_user = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
                    delta = new_user - current_date
                    user.subscription.activate(days=delta.days)

            await session.flush([user, user.subscription])
            await session.commit()
            old_text = await self._format_user_text(user, "edit_user")
            await query.message.edit_text(
                f"{old_text}\n{'*' * 20}\nРоль пользователя изменена на {role_name} ✅",
                reply_markup=user_navigation_kb(
                    filter_type=role_name,
                    index=callback_data.index,
                    total=0,
                    telegram_id=user.telegram_id,
                ),
            )

    @connection()
    @BaseRouter.log_method
    async def sub_select_callback(
        self,
        query: CallbackQuery,
        session: AsyncSession,
        callback_data: UserPageCB,
        state: FSMContext,
    ) -> None:
        """Изменяет срок подписки пользователя.

        Args:
            query (CallbackQuery): Объект колбэка.
            session (AsyncSession): Сессия базы данных.
            callback_data (UserPageCB): Данные из callback кнопки.
            state (FSMContext): Контекст состояний FSM.

        Raises
            ValueError: Если пользователь не найден.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await state.clear()
            months = callback_data.month
            user_id = callback_data.telegram_id
            if user_id is None or months is None:
                raise ValueError("Необходимо передать в запрос telegram_id/month")
            user_schema = SUserTelegramID(telegram_id=int(user_id))
            user = await UserDAO.find_one_or_none(session=session, filters=user_schema)
            if user is None:
                raise ValueError(f"Не нашел такого пользователя({user_id}")
            months = int(months)
            subscription = user.subscription
            if subscription.is_active:
                subscription.extend(months=months)
            await session.flush(
                [
                    user,
                ]
            )
            await session.commit()
            old_text = await self._format_user_text(user, "edit_user")
            if subscription.is_active:
                await query.message.edit_text(
                    f"{old_text}\n"
                    f"{'*' * 10}\n"
                    f"Подписка пользователя изменена на {months} месяц(ев) ✅",
                    reply_markup=admin_user_control_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )
            else:
                await query.message.edit_text(
                    f"{old_text}\n{'*' * 10}\nПодписка пользователя не активирована 🔒",
                    reply_markup=admin_user_control_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )

    @connection()
    @BaseRouter.log_method
    async def cansel_callback(
        self,
        query: CallbackQuery,
        session: AsyncSession,
        callback_data: UserPageCB,
        state: FSMContext,
    ) -> None:
        """Отменяет выбор роли или подписки и возвращает навигацию по пользователям.

        Args:
            query (CallbackQuery): Объект колбэка.
            session (AsyncSession): Сессия базы данных.
            callback_data (UserPageCB): Данные из callback кнопки.
            state (FSMContext): Контекст состояний FSM.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await state.clear()
            await query.answer()
            user_id = callback_data.telegram_id
            old_text = query.message.text
            users = await self._get_users_by_filter(session, callback_data.filter_type)
            await query.message.edit_text(
                text=old_text,
                reply_markup=user_navigation_kb(
                    filter_type=callback_data.filter_type,
                    index=callback_data.index,
                    total=len(users),
                    telegram_id=user_id,
                ),
            )

    @connection()
    @BaseRouter.log_method
    async def show_filtered_users(
        self, query: CallbackQuery, callback_data: AdminCB, session: AsyncSession
    ) -> None:
        """Обрабатывает выбор фильтра пользователей (админы, founder и т.д.).

        Загружает пользователей по выбранному фильтру и показывает первого пользователя
        с клавиатурой навигации.

        Args:
            query (CallbackQuery): Объект колбэка.
            callback_data (AdminCB): Данные callback-кнопки.
            session (AsyncSession): Асинхронная сессия базы данных.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await query.answer()
            users = await self._get_users_by_filter(session, callback_data.filter_type)

            if not users:
                await query.message.edit_text("Пользователи не найдены.")
                return

            user = users[0]
            user_text = await self._format_user_text(user)
            text = f"{user_text}\n\n Пользователь 1 из {len(users)}"

            kb = user_navigation_kb(
                filter_type=callback_data.filter_type,
                index=0,
                total=len(users),
                telegram_id=user.telegram_id,
            )
            await query.message.edit_text(text, reply_markup=kb)

    @connection()
    @BaseRouter.log_method
    async def user_page_callback(
        self, query: CallbackQuery, callback_data: UserPageCB, session: AsyncSession
    ) -> None:
        """Навигация между пользователями по фильтру.

        Загружает пользователей по фильтру и отображает выбранного пользователя
        с клавиатурой навигации.

        Args:
            query (CallbackQuery): Объект колбэка.
            callback_data (UserPageCB): Данные callback-кнопки.
            session (AsyncSession): Асинхронная сессия базы данных.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await query.answer()
            users = await self._get_users_by_filter(session, callback_data.filter_type)

            if not users:
                await query.message.edit_text("Пользователи не найдены.")
                return

            index = min(callback_data.index, len(users) - 1)
            user = users[index]
            user_text = await self._format_user_text(user)
            text = f"{user_text}\n\n Пользователь {index + 1} из {len(users)}"

            kb = user_navigation_kb(
                callback_data.filter_type, index, len(users), user.telegram_id
            )
            await query.message.edit_text(text, reply_markup=kb)
