from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery
from loguru import logger

from bot.admin.router import (
    AdminStates,
    _format_user_text,
    _get_users_by_filter,
    admin_action_callback,
    role_select_callback,
)


@pytest.mark.asyncio
@pytest.mark.admin
async def test_get_users_by_filter_all(monkeypatch):
    """Тестирует получение всех пользователей (filter_type='all')."""

    # Мокаем объекты User и UserRole
    fake_user = MagicMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [fake_user]

    # Мокаем сессию и метод execute
    session = AsyncMock()
    session.execute.return_value = fake_result

    # Вызываем функцию
    result = await _get_users_by_filter(session, filter_type="all")

    # Проверяем
    session.execute.assert_awaited_once()
    fake_result.scalars.assert_called_once()
    assert result == [fake_user]


@pytest.mark.asyncio
@pytest.mark.admin
async def test_get_users_by_filter_with_filter(monkeypatch):
    """Тестирует получение пользователей по фильтру (например, filter_type='admin')."""

    fake_user = MagicMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [fake_user]

    session = AsyncMock()
    session.execute.return_value = fake_result

    result = await _get_users_by_filter(session, filter_type="admin")

    session.execute.assert_awaited_once()
    fake_result.scalars.assert_called_once()
    assert result == [fake_user]


@pytest.mark.asyncio
@pytest.mark.admin
async def test_format_user_text_full(monkeypatch):
    """Тестирует корректное форматирование при наличии всех данных."""

    # Мокаем шаблон
    monkeypatch.setattr(
        "bot.users.router.m_admin",
        {
            "user": "Имя: {first_name}, Фамилия: {last_name}, Ник: {username}, "
            "ID: {telegram_id}, Роли: {roles}, Подписка: {subscription}"
        },
    )

    # Создаём фейкового пользователя
    user = MagicMock()
    user.first_name = "Иван"
    user.last_name = "Петров"
    user.username = "ivan123"
    user.telegram_id = 777
    user.roles = ["admin", "user"]
    user.subscription = "active"

    # Вызываем тестируемую функцию
    result = await _format_user_text(user)

    # Проверяем корректность форматирования
    assert "Иван" in result
    assert "Петров" in result
    assert "ivan123" in result
    assert "777" in result
    assert "admin,user" in result
    assert "active" in result


@pytest.mark.asyncio
@pytest.mark.admin
async def test_format_user_text_missing_fields(monkeypatch):
    """Тестирует замену None и пустых значений на '-'."""

    monkeypatch.setattr(
        "bot.users.router.m_admin",
        {
            "user": "{first_name} {last_name} {username} {telegram_id} {roles} {subscription}"
        },
    )

    user = MagicMock()
    user.first_name = None
    user.last_name = ""
    user.username = None
    user.telegram_id = None
    user.roles = []
    user.subscription = None

    result = await _format_user_text(user)

    # Проверяем, что все поля заменены на '-'
    assert "<b>Имя:</b> - -\n" in result


@pytest.mark.asyncio
@pytest.mark.admin
async def test_format_user_text_custom_key(monkeypatch):
    """Тестирует использование шаблона по кастомному ключу."""

    monkeypatch.setattr(
        "bot.users.router.m_admin",
        {"edit_user": "Пользователь {first_name} ({telegram_id})"},
    )

    user = MagicMock()
    user.first_name = "Ольга"
    user.telegram_id = 123
    user.last_name = user.username = user.roles = user.subscription = None

    result = await _format_user_text(user, key="edit_user")

    assert "Ольга" in result
    assert "123" in result


@pytest.mark.asyncio
@pytest.mark.admin
async def test_admin_action_callback_role_change(monkeypatch, session, fake_state):
    """Проверяет ветку 'role_change'."""
    import inspect

    import bot.admin.router

    logger.error(inspect.getsourcefile(bot.admin.router.admin_action_callback))
    # 1. Мокаем внешние зависимости
    fake_user = MagicMock()
    monkeypatch.setattr(
        "bot.admin.router.UserDAO.find_one_or_none",
        AsyncMock(return_value=fake_user),
    )
    monkeypatch.setattr(
        "bot.admin.router._format_user_text",
        AsyncMock(return_value="Тестовый текст пользователя"),
    )
    monkeypatch.setattr(
        "bot.admin.router.role_selection_kb",
        MagicMock(return_value="fake_keyboard"),
    )
    monkeypatch.setattr(
        "bot.admin.router.subscription_selection_kb",
        MagicMock(return_value="sub_keyboard"),
    )
    # 2. Мокаем query и message
    fake_message = AsyncMock()
    fake_query = AsyncMock()
    fake_query.message = fake_message
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    # 3. Формируем callback_data
    callback_data = MagicMock()
    callback_data.action = "role_change"
    callback_data.telegram_id = 123
    callback_data.filter_type = "admin"
    callback_data.index = 0

    # 4. Мокаем session (он не используется внутри напрямую)
    # fake_session = AsyncMock()

    # 5. Вызываем тестируемую функцию
    await admin_action_callback(
        query=fake_query, state=fake_state, callback_data=callback_data
    )

    # 6. Проверки
    fake_query.answer.assert_awaited_once_with("Отработал")
    fake_state.set_state.assert_awaited_once_with(AdminStates.select_role)
    fake_message.edit_text.assert_awaited_once()
    args, kwargs = fake_message.edit_text.call_args
    assert "Выберите новую роль" in args[0]
    assert kwargs["reply_markup"] == "fake_keyboard"


@pytest.mark.asyncio
@pytest.mark.admin
async def test_admin_action_callback_sub_manage(monkeypatch, session, fake_state):
    """Проверяет ветку 'sub_manage'."""

    fake_user = MagicMock()
    monkeypatch.setattr(
        "bot.admin.router.UserDAO.find_one_or_none",
        AsyncMock(return_value=fake_user),
    )
    monkeypatch.setattr(
        "bot.admin.router._format_user_text",
        AsyncMock(return_value="Текст пользователя"),
    )
    monkeypatch.setattr(
        "bot.admin.router.subscription_selection_kb",
        MagicMock(return_value="fake_sub_kb"),
    )

    fake_message = AsyncMock()
    fake_query = AsyncMock()
    fake_query.message = fake_message
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    callback_data = MagicMock()
    callback_data.action = "sub_manage"
    callback_data.telegram_id = 123
    callback_data.filter_type = "user"
    callback_data.index = 1

    await admin_action_callback(
        query=fake_query, state=fake_state, callback_data=callback_data
    )

    fake_query.answer.assert_awaited_once_with("Отработал")
    fake_state.set_state.assert_awaited_once_with(AdminStates.select_period)
    fake_message.edit_text.assert_awaited_once()
    args, kwargs = fake_message.edit_text.call_args
    assert "срок подписки" in args[0]
    assert kwargs["reply_markup"] == "fake_sub_kb"


@pytest.mark.asyncio
@pytest.mark.admin
async def test_admin_action_callback_no_telegram_id(monkeypatch, session, fake_state):
    """Проверяет, что выбрасывается ошибка, если нет telegram_id."""

    fake_query = AsyncMock()
    fake_query.from_user.id = 111
    fake_query.answer = AsyncMock()

    callback_data = MagicMock()
    callback_data.action = "role_change"
    callback_data.telegram_id = None

    with pytest.raises(ValueError, match="Необходимо передать в запрос telegram_id"):
        await admin_action_callback(
            query=fake_query, state=fake_state, callback_data=callback_data
        )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_role_select_callback(monkeypatch, session, fake_state):
    """Тестируем роль пользователя."""

    # Мокаем пользователя и роль
    fake_user = MagicMock()
    fake_role = MagicMock()
    fake_role.name = "founder"

    # Мокаем datetime чтобы год был 2025
    import datetime

    class FakeDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 6, 1, tzinfo=tz)

    monkeypatch.setattr(datetime, "datetime", FakeDateTime)
    fake_user.roles = []
    fake_user.subscription = MagicMock()
    fake_user.subscription.activate = MagicMock()

    monkeypatch.setattr(
        "bot.admin.router.UserDAO.find_one_or_none", AsyncMock(return_value=fake_user)
    )
    monkeypatch.setattr(
        "bot.admin.router.RoleDAO.find_one_or_none", AsyncMock(return_value=fake_role)
    )
    monkeypatch.setattr(
        "bot.admin.router._format_user_text",
        AsyncMock(return_value="Тестовый текст пользователя"),
    )
    monkeypatch.setattr(
        "bot.admin.router.user_navigation_kb", MagicMock(return_value="fake_keyboard")
    )

    # Мокаем query и message
    fake_message = AsyncMock()
    fake_query = AsyncMock(spec=CallbackQuery)
    fake_query.message = fake_message
    fake_query.from_user = MagicMock()
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    # Формируем callback_data
    callback_data = MagicMock()
    callback_data.filter_type = "founder"
    callback_data.telegram_id = 123
    callback_data.index = 0

    # Вызываем функцию
    await role_select_callback(query=fake_query, callback_data=callback_data)

    # Проверки
    assert fake_user.roles == [fake_role]
    fake_user.subscription.activate.assert_called_once()
    fake_message.edit_text.assert_awaited_once()
    args, kwargs = fake_message.edit_text.call_args
    assert "Роль пользователя изменена на founder ✅" in args[0]
    assert kwargs["reply_markup"] == "fake_keyboard"


@pytest.mark.asyncio
@pytest.mark.admin
async def test_sub_select_callback(monkeypatch, session):
    from bot.admin.router import sub_select_callback

    # 1. Мокаем пользователя и подписку
    fake_user = MagicMock()
    fake_subscription = MagicMock()
    fake_subscription.is_active = True
    fake_subscription.extend = MagicMock()
    fake_user.subscription = fake_subscription

    # 2. Мокаем DAO и утилиты
    monkeypatch.setattr(
        "bot.admin.router.UserDAO.find_one_or_none", AsyncMock(return_value=fake_user)
    )
    monkeypatch.setattr(
        "bot.admin.router._format_user_text",
        AsyncMock(return_value="Текст пользователя"),
    )
    monkeypatch.setattr(
        "bot.admin.router.admin_user_control_kb",
        MagicMock(return_value="fake_keyboard"),
    )

    # 3. Мокаем query
    fake_message = AsyncMock()
    fake_query = AsyncMock(spec=CallbackQuery)
    fake_query.message = fake_message
    fake_query.from_user = MagicMock()
    fake_query.from_user.id = 999

    # 4. Формируем callback_data
    callback_data = MagicMock()
    callback_data.month = 3
    callback_data.telegram_id = 123
    callback_data.index = 0
    callback_data.filter_type = "admin"

    # 6. Вызываем функцию
    await sub_select_callback(query=fake_query, callback_data=callback_data)

    # 7. Проверки
    fake_subscription.extend.assert_called_once_with(months=3)
    fake_message.edit_text.assert_awaited_once()
    args, kwargs = fake_message.edit_text.call_args
    assert "Подписка пользователя изменена на 3 месяц(ев)" in args[0]
    assert kwargs["reply_markup"] == "fake_keyboard"


@pytest.mark.asyncio
@pytest.mark.admin
async def test_cansel_callback(monkeypatch, session):
    from bot.admin.router import cansel_callback

    # 1. Мокаем зависимые функции
    monkeypatch.setattr(
        "bot.admin.router._get_users_by_filter",
        AsyncMock(return_value=[MagicMock(), MagicMock()]),
    )
    monkeypatch.setattr(
        "bot.admin.router.user_navigation_kb",
        MagicMock(return_value="fake_keyboard"),
    )

    # 2. Мокаем ChatActionSender.typing
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    monkeypatch.setattr(
        "bot.admin.router.ChatActionSender.typing",
        lambda bot, chat_id: AsyncContextManagerMock(),
    )

    # 3. Мокаем query и message
    fake_message = AsyncMock()
    fake_message.text = "Старый текст"
    fake_query = AsyncMock(spec=CallbackQuery)
    fake_query.message = fake_message
    fake_query.from_user = MagicMock()
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    # 4. Формируем callback_data
    callback_data = MagicMock()
    callback_data.telegram_id = 123
    callback_data.filter_type = "admin"
    callback_data.index = 0

    # 5. Вызываем функцию
    await cansel_callback(query=fake_query, callback_data=callback_data)

    # 6. Проверки
    fake_query.answer.assert_awaited_once()
    fake_message.edit_text.assert_awaited_once()
    args, kwargs = fake_message.edit_text.call_args
    assert kwargs["text"] == "Старый текст"
    assert kwargs["reply_markup"] == "fake_keyboard"


@pytest.mark.asyncio
@pytest.mark.admin
async def test_show_filtered_users(monkeypatch, session):
    from bot.admin.router import show_filtered_users

    # 1. Мокаем зависимые функции
    fake_user = MagicMock()
    fake_user.telegram_id = 123
    monkeypatch.setattr(
        "bot.admin.router._get_users_by_filter", AsyncMock(return_value=[fake_user])
    )
    monkeypatch.setattr(
        "bot.admin.router._format_user_text",
        AsyncMock(return_value="Фейковый текст пользователя"),
    )
    monkeypatch.setattr(
        "bot.admin.router.user_navigation_kb", MagicMock(return_value="fake_keyboard")
    )

    # 2. Мокаем ChatActionSender.typing
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    monkeypatch.setattr(
        "bot.admin.router.ChatActionSender.typing",
        lambda bot, chat_id: AsyncContextManagerMock(),
    )

    # 3. Мокаем query и message
    fake_message = AsyncMock()
    fake_query = AsyncMock(spec=CallbackQuery)
    fake_query.message = fake_message
    fake_query.from_user = MagicMock()
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    # 4. Формируем callback_data
    callback_data = MagicMock()
    callback_data.filter_type = "admin"

    # 5. Вызываем функцию
    await show_filtered_users(query=fake_query, callback_data=callback_data)

    # 6. Проверки
    fake_query.answer.assert_awaited_once()
    fake_message.edit_text.assert_awaited_once()

    args, kwargs = fake_message.edit_text.call_args
    # Поскольку используем позиционные аргументы
    assert "Фейковый текст пользователя" in args[0] or kwargs.get("text") is not None
    assert (
        kwargs.get("reply_markup", args[1] if len(args) > 1 else None)
        == "fake_keyboard"
    )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_user_page_callback(monkeypatch, session):
    from bot.admin.router import user_page_callback

    # 1. Мокаем зависимые функции
    fake_user_1 = MagicMock()
    fake_user_1.telegram_id = 123
    fake_user_2 = MagicMock()
    fake_user_2.telegram_id = 456

    monkeypatch.setattr(
        "bot.admin.router._get_users_by_filter",
        AsyncMock(return_value=[fake_user_1, fake_user_2]),
    )
    monkeypatch.setattr(
        "bot.admin.router._format_user_text",
        AsyncMock(return_value="Фейковый текст пользователя"),
    )
    monkeypatch.setattr(
        "bot.admin.router.user_navigation_kb", MagicMock(return_value="fake_keyboard")
    )

    # 2. Мокаем ChatActionSender.typing
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    monkeypatch.setattr(
        "bot.admin.router.ChatActionSender.typing",
        lambda bot, chat_id: AsyncContextManagerMock(),
    )

    # 3. Мокаем query и message
    fake_message = AsyncMock()
    fake_query = AsyncMock(spec=CallbackQuery)
    fake_query.message = fake_message
    fake_query.from_user = MagicMock()
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    # 4. Формируем callback_data
    callback_data = MagicMock()
    callback_data.filter_type = "admin"
    callback_data.index = 1  # выбираем второго пользователя

    # 5. Вызываем функцию
    await user_page_callback(query=fake_query, callback_data=callback_data)

    # 6. Проверки
    fake_query.answer.assert_awaited_once()
    fake_message.edit_text.assert_awaited_once()

    args, kwargs = fake_message.edit_text.call_args
    assert "Фейковый текст пользователя" in args[0] or kwargs.get("text") is not None
    assert "Пользователь 2 из 2" in args[0]
    assert (
        kwargs.get("reply_markup", args[1] if len(args) > 1 else None)
        == "fake_keyboard"
    )


@pytest.mark.asyncio
@pytest.mark.admin
async def test_user_page_callback_empty(monkeypatch, session):
    """Проверка случая, когда пользователей нет."""
    from bot.admin.router import user_page_callback

    monkeypatch.setattr(
        "bot.admin.router._get_users_by_filter", AsyncMock(return_value=[])
    )

    # Мокаем ChatActionSender.typing
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    monkeypatch.setattr(
        "bot.admin.router.ChatActionSender.typing",
        lambda bot, chat_id: AsyncContextManagerMock(),
    )

    fake_message = AsyncMock()
    fake_query = AsyncMock(spec=CallbackQuery)
    fake_query.message = fake_message
    fake_query.from_user = MagicMock()
    fake_query.from_user.id = 999
    fake_query.answer = AsyncMock()

    callback_data = MagicMock()
    callback_data.filter_type = "admin"
    callback_data.index = 0

    await user_page_callback(query=fake_query, callback_data=callback_data)

    fake_query.answer.assert_awaited_once()
    fake_message.edit_text.assert_awaited_once()
    args, kwargs = fake_message.edit_text.call_args
    assert "Пользователи не найдены." in args[0]
