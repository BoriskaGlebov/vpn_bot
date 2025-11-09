from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from bot.subscription.models import Subscription
from bot.users.dao import RoleDAO, UserDAO
from bot.users.models import Role
from bot.users.models import User as DBUser
from bot.users.router import UserRouter, UserStates, m_admin, m_error, m_start
from bot.users.schemas import SUserTelegramID


@pytest.mark.asyncio
@pytest.mark.users
@pytest.mark.integration
async def test_cmd_start_new_user_real_db(
    test_bot, fake_logger, fake_redis, make_fake_message, session, fake_state
):
    """Интеграционный тест: новый пользователь сохраняется в реальную тестовую БД."""
    user_router = UserRouter(bot=test_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=1234577)
    users_before = await UserDAO.find_all(session=session)
    role_user = Role(name="user")
    session.add(role_user)
    await session.commit()

    await user_router.cmd_start(message=fake_message, session=session, state=fake_state)
    schema = SUserTelegramID(telegram_id=1234577)
    user = await UserDAO.find_one_or_none(session=session, filters=schema)
    assert user is not None
    assert user.telegram_id == 1234577

    roles = await RoleDAO.find_all(session=session)
    assert any(r.name == "user" for r in roles)

    fake_state.set_state.assert_awaited_once_with(UserStates.press_start)
    assert fake_message.answer.await_count == 2

    expected_first = m_start["welcome"]["first"][0].format(username=user.first_name)
    expected_second = m_start["welcome"]["first"][1]

    calls = fake_message.answer.call_args_list
    first_text = calls[0].args[0]
    second_text = calls[1].args[0]

    assert first_text == expected_first
    assert second_text == expected_second
    new_users = await UserDAO.find_all(session=session)
    assert len(new_users) == (len(users_before) + 1)


# TODO короче надо убирать пользваоетелй между тестами это жуть какаято так тестировать
@pytest.mark.asyncio
@pytest.mark.users
async def test_cmd_start_existing_user_real_db(
    test_bot, fake_logger, fake_redis, make_fake_message, session, fake_state
):
    """Интеграционный тест: уже зарегистрированный пользователь вызывает /start."""
    user_router = UserRouter(bot=test_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=1234588)
    exists_role = await session.scalar(select(Role).where(Role.name == "user"))
    if exists_role is None:
        role_user = Role(name="user")
        session.add(role_user)
        await session.commit()

    exists_user = await session.scalar(
        select(DBUser).where(DBUser.telegram_id == 1234588)
    )
    if exists_user is None:
        user = DBUser(
            telegram_id=1234588,
            username="username_1234588",
            first_name="first_name_1234588",
        )
        session.add(user)
        await session.flush()
        subscription = Subscription(user_id=user.id)
        session.add(subscription)
        await session.commit()

    users = await UserDAO.find_all(session=session)
    old_len = len(users)
    # assert users[0].telegram_id == 1234588
    assert any(user_new.telegram_id == 1234588 for user_new in users)

    await user_router.cmd_start(message=fake_message, session=session, state=fake_state)

    users_after = await UserDAO.find_all(session=session)
    new_user = len(users_after)
    assert new_user == old_len

    fake_state.set_state.assert_awaited_once_with(UserStates.press_start)
    assert fake_message.answer.await_count == 2

    expected_first = m_start["welcome"]["again"][0].format(username=users[0].first_name)
    expected_second = m_start["welcome"]["again"][1]

    calls = fake_message.answer.call_args_list
    first_text = calls[0].args[0]
    second_text = calls[1].args[0]

    assert first_text == expected_first
    assert second_text == expected_second


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_not_admin_real_db(
    test_bot, fake_logger, fake_redis, make_fake_message, session, fake_state
):
    """Интеграционный тест: пользователь не админ — доступ запрещён."""
    user_router = UserRouter(bot=test_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=1234544)
    test_user = DBUser(
        telegram_id=1234544,
        username="testuser_1234544",
        first_name="test_first_name_1234544",
    )
    session.add(test_user)
    await session.commit()
    test_bot.send_message = AsyncMock()

    await user_router.admin_start(message=fake_message, state=fake_state)

    fake_state.clear.assert_awaited_once()
    fake_state.set_state.assert_not_awaited()

    fake_message.answer.assert_awaited_once()
    args, kwargs = fake_message.answer.await_args
    expected_text = m_admin["off"]
    assert expected_text == kwargs["text"]

    test_bot.send_message.assert_awaited_once()
    expected_text2 = m_error["admin_only"]
    args, kwargs = test_bot.send_message.await_args
    assert expected_text2 == kwargs["text"]


@pytest.mark.asyncio
@pytest.mark.users
async def test_admin_start_is_admin_real_db(
    test_bot,
    test_admin_id,
    fake_logger,
    fake_redis,
    make_fake_message,
    session,
    fake_state,
):
    """Интеграционный тест: админ успешно проходит и получает сообщение."""
    user_router = UserRouter(bot=test_bot, logger=fake_logger, redis_manager=fake_redis)
    fake_message = make_fake_message(user_id=test_admin_id)
    user_filter = SUserTelegramID(telegram_id=test_admin_id)
    test_user = await UserDAO.find_one_or_none(session=session, filters=user_filter)
    if test_user is None:
        test_user = DBUser(
            telegram_id=test_admin_id,
            username=f"testuser_{test_admin_id}",
            first_name=f"test_first_name_{test_admin_id}",
        )
        session.add(test_user)
        await session.commit()

    await user_router.admin_start(message=fake_message, state=fake_state)

    fake_state.clear.assert_awaited_once()
    fake_state.set_state.assert_awaited_once()

    test_bot.send_message = AsyncMock()

    await user_router.admin_start(message=fake_message, state=fake_state)
    assert test_bot.send_message.await_count == 2
    calls = test_bot.send_message.await_args_list

    first_call_kwargs = calls[0].kwargs
    second_call_kwargs = calls[1].kwargs

    expected_text = m_admin["on"][0]
    expected_text2 = m_admin["on"][1]

    assert first_call_kwargs["text"] == expected_text
    assert second_call_kwargs["text"] == expected_text2
