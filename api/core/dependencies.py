# # bot/core/dependencies.py
# from typing import AsyncGenerator
#
# from fastapi import Depends
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from bot.database import async_session
#
#
# async def get_session() -> AsyncGenerator[AsyncSession, None]:
#     """FastAPI Dependency для получения асинхронной сессии SQLAlchemy.
#
#     Используется в маршрутах для автоматической работы с транзакцией.
#     """
#     async with async_session() as session:
#         async with session.begin():  # Начинаем транзакцию
#             yield session
