from unittest.mock import AsyncMock, MagicMock, call

import pytest

from bot.admin.enums import ActionEnum
from bot.admin.keyboards.inline_kb import AdminCB, UserPageCB
from bot.admin.router import AdminRouter, AdminStates
from bot.app_error.base_error import SubscriptionNotFoundError
from shared.enums.admin_enum import RoleEnum


@pytest.mark.asyncio
@pytest.mark.admin
async def test_admin_action_callback_role_change(
    fake_bot,
    fake_logger,
    fake_state,
    make_fake_query,
):
    # ---- Мокаем admin_service ----
    admin_service = AsyncMock()
    admin_service.get_user_by_telegram_id = AsyncMock(
        return_value={"id": 123, "username": "test_user"}
    )
    admin_service.format_user_text = AsyncMock(return_value="OLD_TEXT")

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    # ---- Формируем callback_data ----
    cb = UserPageCB(
        action=ActionEnum.ROLE_CHANGE,
        telegram_id=123,
        index=0,
        filter_type=RoleEnum.USER,
    )

    # ---- Создаём query ----
    query = make_fake_query(user_id=999, data="role_change", username="await ")

    # ---- Вызываем метод ----
    await router.admin_action_callback(
        query=query,
        state=fake_state,
        callback_data=cb,
    )

    # ---- Проверяем обработку ----
    query.answer.assert_awaited_with("Выбрал поменять роль.")

    fake_state.set_state.assert_awaited_with(AdminStates.select_role)
    #
    assert query.message.edit_text.await_count == 1
    msg_text, kwargs = (
        query.message.edit_text.await_args.args[0],
        query.message.edit_text.await_args.kwargs,
    )

    # обновлённый текст
    assert "OLD_TEXT" in msg_text
    assert "Выберите новую роль" in msg_text

    # проверяем клавиатуру (просто что она передана)
    assert "reply_markup" in kwargs

    admin_service.get_user_by_telegram_id.assert_awaited_with(telegram_id=123)
    admin_service.format_user_text.assert_awaited()

    # проверяем лог
    fake_logger.bind.assert_called()
    fake_logger.bind.return_value.info.assert_called()


@pytest.mark.asyncio
@pytest.mark.admin
async def test_admin_action_callback_sub_manage(
    fake_bot,
    fake_logger,
    make_fake_query,
    fake_state,
):
    admin_service = AsyncMock()
    admin_service.get_user_by_telegram_id = AsyncMock(
        return_value={"id": 777, "username": "test_user2"}
    )
    admin_service.format_user_text = AsyncMock(return_value="OLD_TEXT_2")

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = UserPageCB(
        action=ActionEnum.SUB_MANAGE,
        telegram_id=777,
        index=1,
        filter_type=RoleEnum.USER,
    )

    query = make_fake_query(user_id=999, data="sub_manage", username="admin")

    await router.admin_action_callback(
        query=query,
        state=fake_state,
        callback_data=cb,
    )

    query.answer.assert_awaited_with("Выбрал изменить срок подписки")
    fake_state.set_state.assert_awaited_with(AdminStates.select_period)

    text = query.message.edit_text.await_args.args[0]
    assert "Выберите срок подписки" in text
    assert "OLD_TEXT_2" in text

    fake_logger.bind.return_value.info.assert_called()


@pytest.mark.asyncio
@pytest.mark.admin
async def test_role_select_callback(
    fake_bot,
    fake_logger,
    make_fake_query,
    fake_state,
):
    # ---- Мокаем admin_service ----
    admin_service = AsyncMock()

    # Возвращаемый user_schema из change_user_role
    user_schema_mock = AsyncMock()
    user_schema_mock.telegram_id = 123

    admin_service.change_user_role.return_value = user_schema_mock
    admin_service.format_user_text.return_value = "UPDATED_TEXT"

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    # ---- callback_data ----
    cb = UserPageCB(
        action=ActionEnum.ROLE_SELECT,
        telegram_id=123,
        index=0,
        filter_type=RoleEnum.FOUNDER,  # это наша новая роль
    )

    # ---- query ----
    query = make_fake_query(
        user_id=999,
        data="role_select",
        username="admin",
    )

    # ---- Вызов ----
    await router.role_select_callback(
        query=query,
        callback_data=cb,
        state=fake_state,
    )

    # ---- Проверяем ответ ----
    query.answer.assert_awaited_with("Поменял роль")

    # ---- Проверяем, что сервис изменил роль ----
    admin_service.change_user_role.assert_awaited_with(
        telegram_id=123,
        role_name=RoleEnum.FOUNDER,
    )

    # ---- Проверяем форматирование текста ----
    admin_service.format_user_text.assert_awaited_with(
        suser=user_schema_mock,
        key="edit_user",
    )

    # ---- Проверяем edit_text ----
    assert query.message.edit_text.await_count == 1

    text, kwargs = (
        query.message.edit_text.await_args.args[0],
        query.message.edit_text.await_args.kwargs,
    )

    assert "UPDATED_TEXT" in text
    assert "Роль пользователя изменена на founder" in text

    # Есть reply_markup
    assert "reply_markup" in kwargs
    assert kwargs["reply_markup"] is not None

    # ---- Проверяем очистку state ----
    fake_state.clear.assert_awaited()

    # ---- Проверяем логи ----
    fake_logger.bind.assert_called()
    fake_logger.bind.return_value.info.assert_called()


@pytest.mark.asyncio
@pytest.mark.admin
async def test_sub_select_callback_success(
    fake_bot,
    fake_logger,
    make_fake_query,
    fake_state,
):
    admin_service = AsyncMock()

    # mocked return user schema
    user_schema_mock = AsyncMock()
    user_schema_mock.telegram_id = 555

    admin_service.extend_user_subscription.return_value = user_schema_mock
    admin_service.format_user_text.return_value = "UPDATED_USER_TEXT"

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = UserPageCB(
        action=ActionEnum.SUB_SELECT,
        telegram_id=555,
        month=3,
        index=1,
        filter_type=RoleEnum.FOUNDER,
    )

    query = make_fake_query(
        user_id=999,
        username="admin",
        data="sub_select",
    )

    await router.sub_select_callback(
        query=query,
        callback_data=cb,
        state=fake_state,
    )

    # extend_user_subscription
    admin_service.extend_user_subscription.assert_awaited_with(
        telegram_id=555,
        months=3,
    )

    # query.answer
    query.answer.assert_awaited_with("Выбрал 3 мес.")

    # format_user_text
    admin_service.format_user_text.assert_awaited_with(
        suser=user_schema_mock,
        key="edit_user",
    )

    # edit_text
    msg = query.message
    assert msg.edit_text.await_count == 1

    text, kwargs = (
        msg.edit_text.await_args.args[0],
        msg.edit_text.await_args.kwargs,
    )

    assert "UPDATED_USER_TEXT" in text
    assert "Подписка продлена на 3 мес." in text
    assert "reply_markup" in kwargs
    assert kwargs["reply_markup"] is not None

    # state cleared
    fake_state.clear.assert_awaited()

    # logging
    fake_logger.bind.assert_called()
    fake_logger.bind.return_value.info.assert_called()


@pytest.mark.asyncio
@pytest.mark.admin
async def test_sub_select_callback_subscription_error(
    fake_bot,
    fake_logger,
    make_fake_query,
    fake_state,
):
    admin_service = AsyncMock()
    admin_service.extend_user_subscription.side_effect = SubscriptionNotFoundError(100)

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = UserPageCB(
        action=ActionEnum.SUB_SELECT,
        telegram_id=100,
        month=1,
        index=0,
        filter_type=RoleEnum.FOUNDER,
    )
    query = make_fake_query(
        user_id=999,
        username="admin",
        data="sub_select",
    )

    await router.sub_select_callback(
        query=query,
        callback_data=cb,
        state=fake_state,
    )

    # extend_user_subscription вызван
    admin_service.extend_user_subscription.assert_awaited()

    # query.answer с текстом ошибки
    query.answer.assert_awaited_with("У пользователя 100 нет подписки / не активна.")
    # edit_text НЕ должен вызываться
    assert query.message.edit_text.await_count == 0

    # state.clear НЕ вызывается
    fake_state.clear.assert_not_awaited()

    # лог ошибки
    fake_logger.error.assert_called()


@pytest.mark.asyncio
@pytest.mark.admin
async def test_cansel_callback(
    fake_bot,
    fake_logger,
    make_fake_query,
):
    # ---- Мокаем сервис ----
    admin_service = AsyncMock()
    admin_service.get_users_by_filter = AsyncMock(
        return_value=[
            {"id": 1, "username": "u1"},
            {"id": 2, "username": "u2"},
        ]
    )

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    # ---- CallbackData ----
    cb = UserPageCB(
        action=ActionEnum.ROLE_CANCEL,
        telegram_id=123,
        index=0,
        filter_type=RoleEnum.USER,
    )

    # ---- Query ----
    query = make_fake_query(
        user_id=999,
        data="cansel",
        username="admin",
    )
    query.message.text = "OLD TEXT"

    # ---- Вызов ----
    await router.cansel_callback(
        query=query,
        callback_data=cb,
    )

    # ---- Проверяем answer() ----
    query.answer.assert_awaited_with("Отмена")

    # ---- Проверяем вызов сервиса ----
    admin_service.get_users_by_filter.assert_awaited_with(
        RoleEnum.USER,
    )

    # ---- Проверяем edit_text ----
    assert query.message.edit_text.await_count == 1
    msg_text, kwargs = (
        query.message.edit_text.await_args.args,
        query.message.edit_text.await_args.kwargs,
    )

    # текст остаётся прежним
    assert kwargs["text"] == "OLD TEXT"
    # есть reply_markup
    assert "reply_markup" in kwargs
    assert (
        call("Админ отменил действие для пользователя 123")
        in fake_logger.bind.return_value.info.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_show_filtered_users_empty(
    fake_bot,
    fake_logger,
    make_fake_query,
    fake_state,
):
    admin_service = AsyncMock()
    admin_service.get_users_by_filter = AsyncMock(return_value=[])
    admin_service.format_user_text = AsyncMock()

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = AdminCB(filter_type=RoleEnum.ADMIN)

    query = make_fake_query(
        user_id=111,
        data="admins",
        username="admin",
    )
    query.message.text = "OLD"

    await router.show_filtered_users(
        query=query,
        callback_data=cb,
        state=fake_state,
    )

    # Ответ callback
    query.answer.assert_awaited_with(f"Выбрал {RoleEnum.ADMIN.value}")

    # Проверяем вызов сервиса
    admin_service.get_users_by_filter.assert_awaited_with(RoleEnum.ADMIN)

    # Должно быть edit_text("Пользователи не найдены.")
    query.message.edit_text.assert_awaited_with("Пользователи не найдены.")

    # Состояние очищено
    fake_state.clear.assert_awaited()

    # Логи: warning внутри метода был
    from unittest.mock import call

    assert (
        call(f"Фильтр {RoleEnum.ADMIN} не вернул пользователей")
        in fake_logger.bind.return_value.warning.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_show_filtered_users_ok(
    fake_bot,
    fake_logger,
    make_fake_query,
    fake_state,
):
    # Данные "пользовательской схемы"
    user_obj = MagicMock()
    user_obj.telegram_id = 123

    admin_service = AsyncMock()
    admin_service.get_users_by_filter = AsyncMock(return_value=[user_obj])
    admin_service.format_user_text = AsyncMock(return_value="USER_TEXT")

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = AdminCB(filter_type=RoleEnum.USER)

    query = make_fake_query(
        user_id=222,
        data="active",
        username="admin",
    )

    await router.show_filtered_users(
        query=query,
        callback_data=cb,
        state=fake_state,
    )

    # --- Проверяем answer() ---
    query.answer.assert_awaited_with(f"Выбрал {RoleEnum.USER.value}")

    # --- Проверяем вызов сервиса ---
    admin_service.get_users_by_filter.assert_awaited_with(
        RoleEnum.USER,
    )

    # --- Проверяем edit_text ---
    assert query.message.edit_text.await_count == 1

    args, kwargs = (
        query.message.edit_text.await_args.args,
        query.message.edit_text.await_args.kwargs,
    )

    text = args[0]
    assert "USER_TEXT" in text
    assert "Пользователь 1 из 1" in text

    # reply_markup существует
    assert "reply_markup" in kwargs

    # --- Проверяем формат_user_text ---
    admin_service.format_user_text.assert_awaited_with(suser=user_obj, key="user")

    # --- Проверяем логирование ---
    from unittest.mock import call

    assert (
        call(f"Фильтр {RoleEnum.USER} вернул 1 пользователей")
        in fake_logger.bind.return_value.info.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_user_page_callback_success(
    fake_bot,
    fake_logger,
    make_fake_query,
):
    # Мокаем сервис
    user_obj = MagicMock()
    user_obj.telegram_id = 555

    admin_service = AsyncMock()
    admin_service.get_users_by_filter.return_value = [user_obj]
    admin_service.format_user_text.return_value = "USER_TEXT"

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = UserPageCB(
        action=ActionEnum.NAVIGATE,
        telegram_id=555,
        filter_type=RoleEnum.USER,
        index=0,
    )

    query = make_fake_query(
        user_id=999,
        data="navigate",
        username="admin",
    )

    await router.user_page_callback(
        query=query,
        callback_data=cb,
    )

    # query.answer
    query.answer.assert_awaited_with("Следующая страница")

    # вызов сервиса
    admin_service.get_users_by_filter.assert_awaited_with(RoleEnum.USER)
    admin_service.format_user_text.assert_awaited_with(suser=user_obj, key="user")

    # edit_text
    assert query.message.edit_text.await_count == 1
    text, kwargs = (
        query.message.edit_text.await_args.args[0],
        query.message.edit_text.await_args.kwargs,
    )
    assert "USER_TEXT" in text
    assert "Пользователь 1 из 1" in text
    assert "reply_markup" in kwargs
    assert kwargs["reply_markup"] is not None

    # лог
    assert (
        call(f"Навигация по пользователям фильтра {RoleEnum.USER}, страница 1")
        in fake_logger.bind.return_value.info.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_user_page_callback_no_users(
    fake_bot,
    fake_logger,
    make_fake_query,
):
    admin_service = AsyncMock()
    admin_service.get_users_by_filter.return_value = []

    router = AdminRouter(fake_bot, fake_logger, admin_service)

    cb = UserPageCB(
        action=ActionEnum.NAVIGATE,
        telegram_id=555,
        filter_type=RoleEnum.USER,
        index=0,
    )

    query = make_fake_query(
        user_id=999,
        data="navigate",
        username="admin",
    )

    await router.user_page_callback(
        query=query,
        callback_data=cb,
    )

    # query.answer
    query.answer.assert_awaited_with("Следующая страница")

    # вызов сервиса
    admin_service.get_users_by_filter.assert_awaited_with(RoleEnum.USER)

    # edit_text
    query.message.edit_text.assert_awaited_with("Пользователи не найдены.")

    # лог warning
    assert (
        call(f"Фильтр {RoleEnum.USER} не вернул пользователей для навигации")
        in fake_logger.bind.return_value.warning.call_args_list
    )
