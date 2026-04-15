# bot/core/dependencies.py
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.api_error import MissingTelegramHeaderError, UserNotFoundHeaderError
from api.core.database import async_session
from api.users.models import User


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения асинхронной сессии SQLAlchemy.

    Используется в маршрутах для автоматической работы с транзакцией.
    """
    async with async_session() as session:
        async with session.begin():
            yield session


api_key_header = APIKeyHeader(name="X-Telegram-Id", auto_error=False)


def get_current_user(request: Request, tg_id: int = Depends(api_key_header)) -> User:
    """Получает текущего пользователя из контекста запроса.

    Эта функция используется в качестве dependency для приватных роутов
    FastAPI и проверяет, что запрос пришёл от зарегистрированного пользователя.

    Args:
        request (Request): объект FastAPI запроса
        tg_id (str, optional): Telegram ID пользователя из заголовка X-Telegram-Id.
            Получается через dependency `APIKeyHeader`.

    Returns
        User: модель пользователя, найденного в базе данных

    Raises
        MissingTelegramHeaderError: если заголовок X-Telegram-Id отсутствует
        UserNotFoundError: если пользователь с указанным telegram_id не найден

    """
    if not tg_id:
        raise MissingTelegramHeaderError()

    user: User | None = getattr(request.state, "user", None)

    if user is None:
        raise UserNotFoundHeaderError(tg_id=tg_id)

    return user
