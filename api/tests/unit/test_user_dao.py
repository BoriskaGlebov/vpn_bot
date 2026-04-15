import asyncio
import datetime

import pytest
from sqlalchemy import StaticPool, event, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from api.app_error.base_error import SubscriptionNotFoundError
from api.core.database import Base  # Declarative Base
from api.subscription.models import Subscription, SubscriptionType
from api.users.dao import RoleDAO, UserDAO
from api.users.models import Role, User
from api.users.schemas import SRole, SSubscription, SUser
from shared.enums.admin_enum import FilterTypeEnum

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Создание event loop для всей тестовой сессии."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def engine():
    """Создание асинхронного движка БД."""
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Важно!
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    """
    Создаёт изолированную сессию для каждого теста.
    Все изменения откатываются после завершения теста,
    даже если внутри вызывается commit().
    """
    async with engine.connect() as connection:
        # Начинаем внешнюю транзакцию
        trans = await connection.begin()

        async_session = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        async with async_session() as session:
            # Создаём вложенную транзакцию (SAVEPOINT)
            nested = await session.begin_nested()

            # Автоматически пересоздаём SAVEPOINT после commit
            @event.listens_for(session.sync_session, "after_transaction_end")
            def restart_savepoint(sess, transaction):
                nonlocal nested
                if transaction.nested and not transaction._parent.nested:
                    nested = sess.begin_nested()

            yield session

            await session.close()

        # Откатываем все изменения после теста
        await trans.rollback()


@pytest.fixture
async def role_user(session: AsyncSession) -> Role:
    result = await session.execute(select(Role).where(Role.name == FilterTypeEnum.USER))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=FilterTypeEnum.USER)
        session.add(role)
        await session.flush()
    return role


@pytest.fixture
async def role_admin(session: AsyncSession) -> Role:
    result = await session.execute(
        select(Role).where(Role.name == FilterTypeEnum.ADMIN)
    )
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=FilterTypeEnum.ADMIN)
        session.add(role)
        await session.flush()
    return role


@pytest.fixture
async def user(session: AsyncSession, role_user: Role) -> User:
    """Фикстура пользователя с подпиской."""
    user = User(
        telegram_id=123456,
        username="test_user",
        first_name="Test",
        last_name="User",
        role=role_user,
    )
    session.add(user)
    await session.flush()

    subscription = Subscription(
        user_id=user.id,
        is_active=True,
    )
    session.add(subscription)
    await session.flush()
    await session.refresh(user)
    return user


pytestmark = pytest.mark.asyncio


async def test_add_role_subscription_user(session, role_user):
    """Проверка создания пользователя с обычной ролью."""
    values_user = SUser(
        telegram_id=111,
        username="new_user",
        first_name="New",
        last_name="User",
    )
    values_role = SRole(name=FilterTypeEnum.USER)

    user = await UserDAO.add_role_subscription(
        session=session,
        values_user=values_user,
        values_role=values_role,
    )
    await session.commit()

    assert user.id is not None
    assert user.role.name == FilterTypeEnum.USER
    assert len(user.subscriptions) == 1
    assert not user.subscriptions[0].is_active


async def test_add_role_subscription_admin(session, role_admin):
    """Проверка создания администратора с активной премиум подпиской."""
    values_user = SUser(
        telegram_id=222,
        username="admin_user",
        first_name="Admin",
        last_name="User",
    )
    values_role = SRole(name=FilterTypeEnum.ADMIN)

    user = await UserDAO.add_role_subscription(
        session=session,
        values_user=values_user,
        values_role=values_role,
    )
    await session.commit()

    subscription = user.subscriptions[0]
    assert user.role.name == FilterTypeEnum.ADMIN
    assert subscription.is_active is True
    assert subscription.type == SubscriptionType.PREMIUM
    assert subscription.end_date is None


async def test_get_users_by_roles_all(session, user):
    """Получение всех пользователей."""
    users = await UserDAO.get_users_by_roles(session, "all")
    assert len(users) >= 1


async def test_get_users_by_roles_filtered(session, user, role_user):
    """Получение пользователей по конкретной роли."""
    users = await UserDAO.get_users_by_roles(
        session,
        FilterTypeEnum.USER,
    )
    assert all(u.role.name == FilterTypeEnum.USER for u in users)


async def test_change_role_to_founder(session, user):
    """Изменение роли на FOUNDER и активация подписки."""
    founder_role = Role(name=FilterTypeEnum.FOUNDER)
    session.add(founder_role)
    user.subscriptions[0].type = SubscriptionType.STANDARD.value
    await session.commit()

    updated_user = await UserDAO.change_role(
        session=session,
        user=user,
        role=founder_role,
    )
    await session.commit()

    assert updated_user.role.name == FilterTypeEnum.FOUNDER
    assert updated_user.subscriptions[0].type == SubscriptionType.STANDARD.value


async def test_extend_subscription_success(session, user):
    """Успешное продление активной подписки."""
    updated_user = await UserDAO.extend_subscription(
        session=session,
        user=user,
        months=3,
    )
    await session.commit()

    assert updated_user.subscriptions[0].is_active is True


async def test_extend_subscription_not_active(session, role_user):
    """Ошибка при продлении неактивной подписки."""
    from api.subscription.models import Subscription
    from api.users.models import User

    user = User(
        telegram_id=999,
        username="inactive_user",
        role=role_user,
    )
    session.add(user)
    await session.flush()

    subscription = Subscription(
        user_id=user.id,
        is_active=False,
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(user)

    with pytest.raises(SubscriptionNotFoundError):
        await UserDAO.extend_subscription(
            session=session,
            user=user,
            months=1,
        )


async def test_find_one_or_none(session, user):
    """Поиск пользователя по telegram_id."""
    from pydantic import BaseModel

    class FilterSchema(BaseModel):
        telegram_id: int

    found_user = await UserDAO.find_one_or_none(
        session=session,
        filters=FilterSchema(telegram_id=user.telegram_id),
    )

    assert found_user is not None
    assert found_user.telegram_id == user.telegram_id


async def test_role_dao_model():
    """Проверка корректности модели RoleDAO."""
    assert RoleDAO.model is Role
