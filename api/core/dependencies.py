# bot/core/dependencies.py
from collections.abc import AsyncGenerator

from core.database import async_session
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения асинхронной сессии SQLAlchemy.

    Используется в маршрутах для автоматической работы с транзакцией.
    """
    async with async_session() as session:
        async with session.begin():  # Начинаем транзакцию
            yield session
