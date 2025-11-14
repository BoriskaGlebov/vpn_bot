import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.admin.router import AdminRouter
from bot.subscription.models import Subscription
from bot.users.models import Role, User


@pytest.mark.asyncio
@pytest.mark.admin
async def test_role_select_callback(
    test_bot, session, make_fake_message, make_fake_query, fake_logger, fake_state
) -> None:
    """Интеграционный тест для метода role_select_callback."""

    # Создаем тестового пользователя и роль в БД
    user = User(
        telegram_id=12345, first_name="first_name_12345", username="username_12345"
    )

    role_old = Role(name="user")
    role_new = Role(name="admin")
    user.roles = [role_old]

    session.add_all([user, role_old, role_new])
    await session.flush()
    subscription = Subscription(user_id=user.id)
    session.add(subscription)
    await session.commit()

    # Создаем реальный callback_query
    query_mock = make_fake_query(user_id=999)

    # Создаем callback_data
    class CallbackDataMock:
        telegram_id = 12345
        filter_type = "admin"
        index = 0
        action = "role_select"

    callback_data = CallbackDataMock()

    # Инициализируем роутер
    router = AdminRouter(bot=test_bot, logger=fake_logger)

    # Вызываем тестируемый метод

    await router.role_select_callback(
        query=query_mock, callback_data=callback_data, session=session, state=fake_state
    )
    stmt = (
        select(User)
        .options(
            selectinload(User.user_roles).selectinload(UserRole.role)
        )  # чтобы roles подгрузились сразу
        .where(User.id == user.id)
    )
    result = await session.execute(stmt)
    updated_user = result.scalar_one()

    # Проверяем, что роль пользователя изменилась
    assert updated_user.roles[0].name == "admin"

    # Проверяем, что сообщение было отредактировано
    query_mock.message.edit_text.assert_called()


@pytest.mark.asyncio
@pytest.mark.admin
@pytest.mark.integration
async def test_sub_select_callback(
    session, test_bot, fake_logger, make_fake_query, fake_state
):
    """Интеграционный тест для метода sub_select_callback."""

    # Создаем пользователя и подписку
    user = User(telegram_id=789, first_name="first_name_789", username="username_789")
    session.add(user)
    await session.flush()  # присвоит user.id

    subscription = Subscription(user_id=user.id)
    subscription.is_active = True  # делаем подписку активной
    session.add(subscription)
    await session.commit()

    # Мокаем CallbackQuery
    query_mock = make_fake_query(user_id=789)

    # Создаем callback_data
    class CallbackDataMock:
        telegram_id = 789
        month = 3
        filter_type = "all"
        index = 0
        action = "sub_select"

    callback_data = CallbackDataMock()

    # Инициализируем роутер
    router = AdminRouter(bot=test_bot, logger=fake_logger)

    # Вызываем метод
    await router.sub_select_callback(
        query=query_mock, session=session, callback_data=callback_data, state=fake_state
    )

    # Проверяем, что срок подписки продлен
    updated_user = await session.get(User, user.id)
    assert updated_user.subscription.is_active
    # Если есть метод extend возвращает новые даты, можно проверить end_date
    assert updated_user.subscription.end_date is not None

    # Проверяем, что сообщение было отредактировано
    query_mock.message.edit_text.assert_called()
