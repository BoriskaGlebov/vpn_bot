from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.enums import ActionEnum
from bot.admin.keyboards.inline_kb import (
    AdminCB,
    UserPageCB,
    admin_user_control_kb,
    role_selection_kb,
    subscription_selection_kb,
    user_navigation_kb,
)
from bot.admin.services import AdminModeKeys, AdminService
from bot.app_error.base_error import SubscriptionNotFoundError
from bot.database import connection
from bot.utils.base_router import BaseRouter


class AdminStates(StatesGroup):  # type: ignore[misc]
    """Состояния администратора при управлении пользователями."""

    select_role: State = State()
    select_period: State = State()


class AdminRouter(BaseRouter):
    """Роутер для обработки действий администратора."""

    def __init__(self, bot: Bot, logger: Logger, admin_service: AdminService) -> None:
        super().__init__(bot, logger)
        self.admin_service = admin_service

    def _register_handlers(self) -> None:
        self.router.callback_query.register(
            self.admin_action_callback,
            or_f(
                UserPageCB.filter(F.action == ActionEnum.ROLE_CHANGE),
                UserPageCB.filter(F.action == ActionEnum.SUB_MANAGE),
            ),
        )
        self.router.callback_query.register(
            self.role_select_callback,
            and_f(
                StateFilter(AdminStates.select_role),
                UserPageCB.filter(F.action == ActionEnum.ROLE_SELECT),
            ),
        )
        self.router.callback_query.register(
            self.sub_select_callback,
            and_f(
                StateFilter(AdminStates.select_period),
                UserPageCB.filter(F.action == ActionEnum.SUB_SELECT),
            ),
        )
        self.router.callback_query.register(
            self.cansel_callback,
            or_f(
                UserPageCB.filter(F.action == ActionEnum.ROLE_CANCEL),
                UserPageCB.filter(F.action == ActionEnum.SUBSCR_CANCEL),
            ),
        )
        self.router.callback_query.register(
            self.show_filtered_users,
            AdminCB.filter(),
        )
        self.router.callback_query.register(
            self.user_page_callback,
            UserPageCB.filter(F.action == ActionEnum.NAVIGATE),
        )

        self.router.message.register(
            self.mistake_handler_user,
            and_f(
                or_f(
                    StateFilter(AdminStates.select_role),
                    StateFilter(AdminStates.select_period),
                ),
                ~F.text.startswith("/"),
            ),
        )

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def admin_action_callback(
        self,
        query: CallbackQuery,
        msg: Message,
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
            msg (Message): Сообщение над которым надо вносить изменения.
            state (FSMContext): Контекст состояний FSM.
            session (AsyncSession): Сессия базы данных.
            callback_data (UserPageCB | None): Данные из callback кнопки.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            user_id: int | None = callback_data.telegram_id
            if user_id is None:
                user_logger.error(
                    "Не передан telegram_id для редактирования пользователя"
                )
                raise ValueError("Необходимо передать в запрос telegram_id")
            user_schema = await self.admin_service.get_user_by_telegram_id(
                session=session, telegram_id=user_id
            )
            old_text = await self.admin_service.format_user_text(
                suser=user_schema, key=AdminModeKeys.EDIT_USER
            )
            if callback_data.action == ActionEnum.ROLE_CHANGE:
                await query.answer("Выбрал поменять роль.")
                await state.set_state(AdminStates.select_role)
                await msg.edit_text(
                    f"{old_text}\nВыберите новую роль для пользователя:",
                    reply_markup=role_selection_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )
                user_logger.info(f"Начал смену роли для пользователя {user_id}")
            elif callback_data.action == ActionEnum.SUB_MANAGE:
                await query.answer("Выбрал изменить срок подписки")
                await state.set_state(AdminStates.select_period)
                await msg.edit_text(
                    f"{old_text}\nВыберите срок подписки для пользователя:",
                    reply_markup=subscription_selection_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )
                user_logger.info(f"Начал управление подпиской пользователя {user_id}")

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def role_select_callback(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: UserPageCB,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        """Изменяет роль пользователя.

        Args:
            query (CallbackQuery): Объект колбэка.
            msg (Message): Сообщение над которым надо вносить изменения.
            callback_data (UserPageCB): Данные из callback кнопки.
            session (AsyncSession): Сессия базы данных.
            state (FSMContext): Контекст состояний FSM.

        Raises
            ValueError: Если пользователь или роль не найдены.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await query.answer("Поменял роль")

            user_id = callback_data.telegram_id
            role_name = callback_data.filter_type

            if user_id is None:
                user_logger.error("Не передан telegram_id для смены роли")
                raise ValueError("Необходимо передать в запрос telegram_id")

            user_schema = await self.admin_service.change_user_role(
                session=session,
                telegram_id=user_id,
                role_name=role_name,
            )

            old_text = await self.admin_service.format_user_text(
                suser=user_schema, key=AdminModeKeys.EDIT_USER
            )
            await msg.edit_text(
                f"{old_text}\nРоль пользователя изменена на {role_name} ✅",
                reply_markup=user_navigation_kb(
                    filter_type=role_name,
                    index=callback_data.index,
                    total=0,
                    telegram_id=user_schema.telegram_id,
                ),
            )
            user_logger.info(f"Смена роли пользователя {user_id} на {role_name} ✅")
            await state.clear()

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def sub_select_callback(
        self,
        query: CallbackQuery,
        msg: Message,
        session: AsyncSession,
        callback_data: UserPageCB,
        state: FSMContext,
    ) -> None:
        """Изменяет срок подписки пользователя.

        Args:
            query (CallbackQuery): Объект колбэка.
            msg (Message): Сообщение над которым надо вносить изменения.
            session (AsyncSession): Сессия базы данных.
            callback_data (UserPageCB): Данные из callback кнопки.
            state (FSMContext): Контекст состояний FSM.

        Raises
            ValueError: Если пользователь не найден.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            user_id = callback_data.telegram_id
            months = callback_data.month

            if user_id is None or months is None:
                user_logger.error("Не передан telegram_id или месяц для подписки")
                raise ValueError("Необходимо передать в запрос telegram_id/month")

            months = int(months)
            try:
                user_schema = await self.admin_service.extend_user_subscription(
                    session=session, telegram_id=user_id, months=months
                )
                await query.answer(f"Выбрал {months} мес.")
                old_text = await self.admin_service.format_user_text(
                    suser=user_schema, key=AdminModeKeys.EDIT_USER
                )

                await msg.edit_text(
                    f"{old_text}\nПодписка продлена на {months} мес. ✅",
                    reply_markup=admin_user_control_kb(
                        filter_type=callback_data.filter_type,
                        index=callback_data.index,
                        telegram_id=user_id,
                    ),
                )
                user_logger.info(
                    f"Подписка пользователя {user_id} продлена на {months} мес."
                )
                await state.clear()
            except SubscriptionNotFoundError as e:
                self.logger.error("Нельзя продлить подписку она не активирована")
                await query.answer(str(e))

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def cansel_callback(
        self,
        query: CallbackQuery,
        msg: Message,
        session: AsyncSession,
        callback_data: UserPageCB,
    ) -> None:
        """Отменяет выбор роли или подписки и возвращает навигацию по пользователям.

        Args:
            query (CallbackQuery): Объект колбэка.
            msg (Message): Сообщение над которым надо вносить изменения.
            session (AsyncSession): Сессия базы данных.
            callback_data (UserPageCB): Данные из callback кнопки.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await query.answer("Отмена")
            user_id = callback_data.telegram_id
            old_text = msg.text or ""
            users_schemas = await self.admin_service.get_users_by_filter(
                session, callback_data.filter_type
            )
            await msg.edit_text(
                text=old_text,
                reply_markup=user_navigation_kb(
                    filter_type=callback_data.filter_type,
                    index=callback_data.index,
                    total=len(users_schemas),
                    telegram_id=user_id,
                ),
            )
            user_logger.info(
                f"Админ отменил действие для пользователя {callback_data.telegram_id}"
            )

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def show_filtered_users(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: AdminCB,
        session: AsyncSession,
        state: FSMContext,
    ) -> None:
        """Обрабатывает выбор фильтра пользователей (админы, founder и т.д.).

        Загружает пользователей по выбранному фильтру и показывает первого пользователя
        с клавиатурой навигации.

        Args:
            query (CallbackQuery): Объект колбэка.
            msg (Message): Сообщение над которым надо вносить изменения.
            callback_data (AdminCB): Данные callback-кнопки.
            session (AsyncSession): Асинхронная сессия базы данных.
            state (FSMContext): Контекст состояний FSM.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            filter_type = callback_data.filter_type
            await query.answer(f"Выбрал {filter_type}")
            users_schemas = await self.admin_service.get_users_by_filter(
                session, filter_type
            )

            if not users_schemas:
                await msg.edit_text("Пользователи не найдены.")
                user_logger.warning(
                    f"Фильтр {callback_data.filter_type} не вернул пользователей"
                )
                await state.clear()
                return
            user_logger.info(
                f"Фильтр {callback_data.filter_type} вернул {len(users_schemas)} пользователей"
            )

            user = users_schemas[0]
            user_text = await self.admin_service.format_user_text(
                suser=user, key=AdminModeKeys.USER
            )
            text = f"{user_text}\n\n Пользователь 1 из {len(users_schemas)}"

            kb = user_navigation_kb(
                filter_type=filter_type,
                index=0,
                total=len(users_schemas),
                telegram_id=user.telegram_id,
            )
            await msg.edit_text(text, reply_markup=kb)

    @connection()
    @BaseRouter.log_method
    @BaseRouter.require_message
    async def user_page_callback(
        self,
        query: CallbackQuery,
        msg: Message,
        callback_data: UserPageCB,
        session: AsyncSession,
    ) -> None:
        """Навигация между пользователями по фильтру.

        Загружает пользователей по фильтру и отображает выбранного пользователя
        с клавиатурой навигации.

        Args:
            query (CallbackQuery): Объект колбэка.
            msg (Message): Сообщение над которым надо вносить изменения.
            callback_data (UserPageCB): Данные callback-кнопки.
            session (AsyncSession): Асинхронная сессия базы данных.

        """
        user_logger = self.logger.bind(
            user=query.from_user.username or query.from_user.id
        )
        async with ChatActionSender.typing(bot=self.bot, chat_id=query.from_user.id):
            await query.answer("Следующая страница")
            users_schemas = await self.admin_service.get_users_by_filter(
                session, callback_data.filter_type
            )

            if not users_schemas:
                user_logger.warning(
                    f"Фильтр {callback_data.filter_type} не вернул пользователей для навигации"
                )
                await msg.edit_text("Пользователи не найдены.")
                return
            user_logger.info(
                f"Навигация по пользователям фильтра {callback_data.filter_type}, страница {callback_data.index + 1}"
            )
            index = min(callback_data.index, len(users_schemas) - 1)
            user = users_schemas[index]
            user_text = await self.admin_service.format_user_text(
                suser=user, key=AdminModeKeys.USER
            )
            text = f"{user_text}\n\n Пользователь {index + 1} из {len(users_schemas)}"

            kb = user_navigation_kb(
                callback_data.filter_type, index, len(users_schemas), user.telegram_id
            )
            await msg.edit_text(text, reply_markup=kb)
