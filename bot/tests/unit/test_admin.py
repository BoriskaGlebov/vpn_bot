import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.router import AdminRouter, AdminStates
from bot.subscription.models import Subscription
from bot.users.models import Role, User, UserRole


@pytest.mark.asyncio
@pytest.mark.admin
async def test_get_users_by_filter(session: AsyncSession):
    """Проверяет, что _get_users_by_filter корректно возвращает пользователей."""

    # --- Подготовка данных ---
    # Создаём роли
    role_admin = Role(name="admin")
    role_user = Role(name="user")

    # Создаём пользователей
    user1 = User(first_name="Alice", telegram_id=111, username="Alice_111")
    user2 = User(first_name="Bob", telegram_id=222, username="Bob_222")

    # Привязываем роли
    user_role1 = UserRole(user=user1, role=role_admin)
    user_role2 = UserRole(user=user2, role=role_user)

    session.add_all([role_admin, role_user, user1, user2, user_role1, user_role2])
    await session.commit()

    # --- Вызов тестируемого метода ---
    result_admins = await AdminRouter._get_users_by_filter(session, "admin")
    result_all = await AdminRouter._get_users_by_filter(session, "all")

    # --- Проверки ---
    assert len(result_admins) == 1
    assert result_admins[0].first_name == "Alice"

    assert len(result_all) == 2
    names = {u.first_name for u in result_all}
    assert names == {"Alice", "Bob"}


@pytest.mark.asyncio
@pytest.mark.admin
async def test_format_user_text(monkeypatch):
    """Проверяет корректное форматирование текста пользователя с объектом подписки."""

    # --- Подменяем шаблон текста в m_admin ---
    fake_template = (
        "Имя: {first_name}\n"
        "Фамилия: {last_name}\n"
        "Юзернейм: {username}\n"
        "ID: {telegram_id}\n"
        "Роли: {roles}\n"
        "Подписка: {subscription}"
    )
    monkeypatch.setattr("bot.admin.router.m_admin", {"user": fake_template})

    # --- Создаём фейкового пользователя ---
    user = User(
        first_name="Alice",
        last_name="Wonder",
        username="alice123",
        telegram_id=42,
    )

    # --- Добавляем роль ---
    role_admin = Role(name="admin")
    user.roles = [role_admin]

    # --- Создаём и привязываем подписку ---
    subscription = Subscription(
        is_active=True,
        start_date=datetime.datetime.now(datetime.UTC),
        end_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=10),
    )
    user.subscription = subscription

    # --- Вызываем тестируемый метод ---
    text = await AdminRouter._format_user_text(user)

    # --- Проверки ---
    assert "Alice" in text
    assert "Wonder" in text
    assert "alice123" in text
    assert "admin" in text
    assert "Активна" in text or "Неактивна" in text  # текст из __str__ Subscription
    assert "Имя:" in text


@pytest.mark.asyncio
@pytest.mark.admin
async def test_fake_query_usage(make_fake_query):
    query = make_fake_query()
    await query.answer("OK")
    await query.message.edit_text("New text")

    query.answer.assert_awaited_once_with("OK")
    query.message.edit_text.assert_awaited_once_with("New text")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action, expected_state",
    [
        ("role_change", AdminStates.select_role),
        ("sub_manage", AdminStates.select_period),
    ],
)
@pytest.mark.admin
async def test_admin_action_callback(
    fake_logger,
    make_fake_query,
    fake_state,
    make_fake_message,
    session,
    fake_bot,
    monkeypatch,
    action,
    expected_state,
):
    """Проверяет, что admin_action_callback корректно обрабатывает role_change и sub_manage."""

    # --- 1️⃣ Подготовка зависимостей ---
    router = AdminRouter(fake_bot, fake_logger)
    fake_user = MagicMock(spec=User)
    fake_message = make_fake_message(user_id=123)

    # --- 2️⃣ Подмена callback_query и callback_data ---
    callback_query = make_fake_query(user_id=123)
    callback_data = MagicMock()
    callback_data.telegram_id = 123
    callback_data.action = action
    callback_data.filter_type = "all"
    callback_data.index = 0

    # --- 3️⃣ Monkeypatch зависимостей ---
    monkeypatch.setattr(
        "bot.admin.router.UserDAO.find_one_or_none",
        AsyncMock(return_value=fake_user),
    )
    monkeypatch.setattr(
        "bot.admin.router.AdminRouter._format_user_text",
        AsyncMock(return_value="old text"),
    )

    fake_kb = MagicMock()
    monkeypatch.setattr("bot.admin.router.role_selection_kb", lambda **_: fake_kb)
    monkeypatch.setattr(
        "bot.admin.router.subscription_selection_kb", lambda **_: fake_kb
    )

    # --- 4️⃣ Вызов тестируемого метода ---
    await router.admin_action_callback(
        query=callback_query,
        state=fake_state,
        session=session,
        callback_data=callback_data,
    )

    # --- 5️⃣ Проверки ---
    fake_state.set_state.assert_awaited_once_with(expected_state)
    callback_query.message.edit_text.assert_awaited_once()

    args, kwargs = callback_query.message.edit_text.call_args
    assert "Выберите" in args[0]
    assert kwargs["reply_markup"] == fake_kb


@pytest.mark.asyncio
@pytest.mark.admin
async def test_role_select_callback_founder(
    fake_logger,
    make_fake_query,
    fake_state,
    make_fake_message,
    session,
    fake_bot,
    monkeypatch,
):
    """Проверяет, что role_select_callback корректно обновляет роль пользователя (founder)."""

    # --- 1️⃣ Подготовка окружения ---
    router = AdminRouter(fake_bot, fake_logger)
    callback_query = make_fake_query(user_id=123)

    callback_data = MagicMock()
    callback_data.filter_type = "founder"
    callback_data.telegram_id = 123
    callback_data.index = 0

    fake_user = MagicMock()
    fake_user.telegram_id = 123
    fake_user.subscription = MagicMock()
    fake_role = MagicMock()
    fake_role.name = "founder"

    # --- 2️⃣ Monkeypatch зависимостей ---
    mock_user_find = AsyncMock(return_value=fake_user)
    mock_role_find = AsyncMock(return_value=fake_role)
    monkeypatch.setattr("bot.admin.router.UserDAO.find_one_or_none", mock_user_find)
    monkeypatch.setattr("bot.admin.router.RoleDAO.find_one_or_none", mock_role_find)

    mock_format = AsyncMock(return_value="formatted user info")
    monkeypatch.setattr("bot.admin.router.AdminRouter._format_user_text", mock_format)

    fake_kb = MagicMock()
    monkeypatch.setattr("bot.admin.router.user_navigation_kb", lambda **_: fake_kb)

    # --- 3️⃣ Вызов тестируемого метода ---
    await router.role_select_callback(
        query=callback_query,
        callback_data=callback_data,
        session=session,
        state=fake_state,
    )

    # --- 4️⃣ Проверки ---
    fake_state.clear.assert_awaited_once()
    mock_user_find.assert_awaited_once()
    mock_role_find.assert_awaited_once()

    # Проверяем, что роль присвоена
    assert fake_user.roles == [fake_role]

    # Проверяем, что подписка активировалась (так как founder)
    fake_user.subscription.activate.assert_called_once()

    # Проверяем, что сообщение изменено
    callback_query.message.edit_text.assert_awaited_once()
    args, kwargs = callback_query.message.edit_text.call_args
    assert "Роль пользователя изменена" in args[0]
    assert "founder" in args[0]
    assert kwargs["reply_markup"] == fake_kb


@pytest.mark.parametrize(
    "is_active, expected_phrase",
    [
        (True, "Подписка пользователя изменена"),
        (False, "Подписка пользователя не активирована"),
    ],
)
@pytest.mark.asyncio
@pytest.mark.admin
async def test_sub_select_callback(
    fake_logger,
    make_fake_query,
    fake_state,
    session,
    fake_bot,
    monkeypatch,
    is_active,
    expected_phrase,
):
    """Проверяет корректную обработку продления или неактивной подписки."""

    # --- 1️⃣ Подготовка окружения ---
    router = AdminRouter(fake_bot, fake_logger)
    callback_query = make_fake_query(user_id=777)

    callback_data = MagicMock()
    callback_data.telegram_id = 777
    callback_data.month = 3
    callback_data.index = 0
    callback_data.filter_type = "all"

    # --- 2️⃣ Моки пользователя и подписки ---
    fake_subscription = MagicMock(spec=Subscription)
    fake_subscription.is_active = is_active

    fake_user = MagicMock(spec=User)
    fake_user.subscription = fake_subscription
    fake_user.telegram_id = 777

    # --- 3️⃣ Monkeypatch зависимостей ---
    mock_user_find = AsyncMock(return_value=fake_user)
    monkeypatch.setattr("bot.admin.router.UserDAO.find_one_or_none", mock_user_find)

    mock_format = AsyncMock(return_value="formatted user info")
    monkeypatch.setattr("bot.admin.router.AdminRouter._format_user_text", mock_format)

    fake_kb = MagicMock()
    monkeypatch.setattr("bot.admin.router.admin_user_control_kb", lambda **_: fake_kb)

    # --- 4️⃣ Вызов тестируемого метода ---
    await router.sub_select_callback(
        query=callback_query,
        session=session,
        callback_data=callback_data,
        state=fake_state,
    )
    # --- 5️⃣ Проверки ---
    fake_state.clear.assert_awaited_once()
    mock_user_find.assert_awaited_once()

    # Проверяем extend() только если подписка активна
    if is_active:
        fake_subscription.extend.assert_called_once_with(months=3)
    else:
        fake_subscription.extend.assert_not_called()

    # Проверяем, что текст сообщения корректный
    callback_query.message.edit_text.assert_awaited_once()
    args, kwargs = callback_query.message.edit_text.call_args
    assert expected_phrase in args[0]
    assert kwargs["reply_markup"] == fake_kb


@pytest.mark.asyncio
async def test_cansel_callback(
    fake_logger,
    make_fake_query,
    fake_state,
    make_fake_message,
    session,
    fake_bot,
    monkeypatch,
):
    """Проверяет корректную работу cansel_callback."""

    # --- 1️⃣ Подготовка окружения ---
    router = AdminRouter(fake_bot, fake_logger)
    fake_message = make_fake_message(user_id=101)
    callback_query = make_fake_query(user_id=101)
    callback_query.message = fake_message

    callback_data = MagicMock()
    callback_data.telegram_id = 101
    callback_data.filter_type = "all"
    callback_data.index = 0

    # --- 2️⃣ Подмена зависимостей ---
    fake_users_list = [MagicMock(), MagicMock()]
    monkeypatch.setattr(
        "bot.admin.router.AdminRouter._get_users_by_filter",
        AsyncMock(return_value=fake_users_list),
    )

    fake_kb = MagicMock()
    monkeypatch.setattr("bot.admin.router.user_navigation_kb", lambda **_: fake_kb)

    # --- 3️⃣ Вызов тестируемого метода ---
    await router.cansel_callback(
        query=callback_query,
        session=session,
        callback_data=callback_data,
        state=fake_state,
    )

    # --- 4️⃣ Проверки ---
    # FSM cleared
    fake_state.clear.assert_awaited_once()
    # Callback answered
    callback_query.answer.assert_awaited_once()
    # Проверяем, что список пользователей получен
    router._get_users_by_filter.assert_awaited_once_with(session, "all")
    # Проверяем редактирование сообщения
    callback_query.message.edit_text.assert_awaited_once()
    args, kwargs = callback_query.message.edit_text.call_args
    assert kwargs["text"] == fake_message.text  # текст остался прежним
    assert kwargs["reply_markup"] == fake_kb


@pytest.mark.asyncio
@pytest.mark.parametrize("users_exist", [True, False])
@pytest.mark.admin
async def test_show_filtered_users(
    fake_logger,
    make_fake_query,
    session,
    fake_bot,
    monkeypatch,
    users_exist,
):
    router = AdminRouter(fake_bot, fake_logger)
    callback_query = make_fake_query(user_id=555)

    callback_data = MagicMock()
    callback_data.filter_type = "all"

    # --- Подмена _get_users_by_filter ---
    if users_exist:
        fake_user = MagicMock()
        fake_user.telegram_id = 555
        monkeypatch.setattr(
            router, "_get_users_by_filter", AsyncMock(return_value=[fake_user])
        )
        monkeypatch.setattr(
            router, "_format_user_text", AsyncMock(return_value="user info")
        )
        fake_kb = MagicMock()
        monkeypatch.setattr("bot.admin.router.user_navigation_kb", lambda **_: fake_kb)
    else:
        monkeypatch.setattr(router, "_get_users_by_filter", AsyncMock(return_value=[]))

    # --- Вызов метода ---
    await router.show_filtered_users(
        query=callback_query,
        callback_data=callback_data,
        session=session,
    )

    # --- Проверки ---
    callback_query.answer.assert_awaited_once()
    callback_query.message.edit_text.assert_awaited_once()

    called_args, called_kwargs = callback_query.message.edit_text.call_args
    if users_exist:
        # Пользователь есть → текст с info и клавиатура
        assert "user info" in called_args[0]
        assert called_kwargs["reply_markup"] == fake_kb
    else:
        # Пользователей нет → сообщение "Пользователи не найдены."
        assert called_args[0] == "Пользователи не найдены."


@pytest.mark.asyncio
@pytest.mark.parametrize("users_exist,index", [(True, 0), (True, 2), (False, 0)])
async def test_user_page_callback(
    fake_logger,
    make_fake_query,
    session,
    fake_bot,
    monkeypatch,
    users_exist,
    index,
):
    router = AdminRouter(fake_bot, fake_logger)
    callback_query = make_fake_query(user_id=777)

    callback_data = MagicMock()
    callback_data.filter_type = "all"
    callback_data.index = index

    # --- Подмена _get_users_by_filter ---
    if users_exist:
        fake_users = []
        for i in range(3):  # создаём 3 пользователей
            u = MagicMock()
            u.telegram_id = 100 + i
            fake_users.append(u)
        monkeypatch.setattr(
            router, "_get_users_by_filter", AsyncMock(return_value=fake_users)
        )
        monkeypatch.setattr(
            router, "_format_user_text", AsyncMock(return_value="user info")
        )
        fake_kb = MagicMock()
        monkeypatch.setattr(
            "bot.admin.router.user_navigation_kb", lambda *a, **kw: fake_kb
        )
    else:
        monkeypatch.setattr(router, "_get_users_by_filter", AsyncMock(return_value=[]))

    # --- Вызов метода ---
    await router.user_page_callback(
        query=callback_query,
        callback_data=callback_data,
        session=session,
    )

    # --- Проверки ---
    callback_query.answer.assert_awaited_once()
    callback_query.message.edit_text.assert_awaited_once()
    called_args, called_kwargs = callback_query.message.edit_text.call_args
    if users_exist:
        # Выбирается правильный индекс пользователя
        actual_index = min(index, 2)  # 2 — последний индекс
        assert f"Пользователь {actual_index + 1} из 3" in called_args[0]
        assert called_kwargs["reply_markup"] == fake_kb
    else:
        assert called_args[0] == "Пользователи не найдены."
