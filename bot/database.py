from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar, cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings_db

engine = create_async_engine(cast(str, settings_db.database_url))

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def connection(isolation_level: str | None = None) -> Callable[[F], F]:
    """Декоратор для автоматического управления асинхронной сессией базы данных и транзакцией.

    Этот декоратор создаёт сессию `AsyncSession`, оборачивает выполнение функции в транзакцию,
    автоматически выполняет commit или rollback при исключении и закрывает сессию после завершения.

    Args:
        isolation_level (str, optional): Уровень изоляции транзакции. Возможные значения:
            - "READ COMMITTED" — по умолчанию, для большинства CRUD-операций.
            - "REPEATABLE READ" — для сложных аналитических запросов или расчётов.
            - "SERIALIZABLE" — полная защита от конкурентных изменений (например, финансы).

    Returns
        function: Декорированная асинхронная функция, которой будет передан аргумент `session` типа `AsyncSession`.

    Examples
        @connection(isolation_level="SERIALIZABLE")
        async def create_user(username: str, session: AsyncSession):
            user = User(username=username)
            session.add(user)

    """

    def decorator(method: F) -> F:
        @wraps(method)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if isinstance(kwargs.get("session"), AsyncSession):
                return await method(*args, **kwargs)
            async with async_session() as session:
                try:
                    if isolation_level:
                        await session.execute(
                            text(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
                        )
                    async with session.begin():
                        return await method(*args, session=session, **kwargs)
                except SQLAlchemyError:
                    await session.rollback()
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator
