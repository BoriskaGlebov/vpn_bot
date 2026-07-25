# bot/core/dependencies.py
import secrets
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.api_error import (
    InvalidInternalSecretError,
    MissingTelegramHeaderError,
)
from api.app_error.base_error import UserNotFoundError
from api.core.config import settings_api
from api.core.database import async_session
from api.users.models import User


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения асинхронной сессии SQLAlchemy.

    Используется в маршрутах для автоматической работы с транзакцией.
    """
    async with async_session() as session:
        async with session.begin():
            yield session


api_key_header = APIKeyHeader(
    name="X-Telegram-Id", scheme_name="TelegramIdHeader", auto_error=False
)

# scheme_name отдельный от api_key_header — иначе оба APIKeyHeader() без явного
# имени схемы регистрируются в OpenAPI под одним и тем же именем класса
# ("APIKeyHeader") и Swagger показывает/принимает только один из двух.
secret_key_header = APIKeyHeader(
    name="X-Internal-Secret", scheme_name="InternalSecretHeader", auto_error=False
)


def get_current_user(
    request: Request,
    tg_id: int = Depends(api_key_header),
    secret_key: str = Depends(secret_key_header),
) -> User:
    """Получает текущего пользователя из контекста запроса.

    Эта функция используется в качестве dependency для приватных роутов
    FastAPI и проверяет, что запрос пришёл от зарегистрированного пользователя.

    Секрет уже проверяется в ``AuthMiddleware`` (это основная защита — запрос
    без него даже не пытается искать пользователя по tg_id). Проверка здесь
    дублирует её на уровне FastAPI-зависимости ради двух вещей: во-первых,
    именно так ``X-Internal-Secret`` попадает в OpenAPI/Swagger как отдельная
    схема авторизации (кнопка Authorize), доступная для проверки прямо из
    документации — раньше секрет был виден только внутри ASGI-middleware,
    которое Swagger не читает. Во-вторых, так пользователь получает понятную
    ошибку именно про секрет, а не общий "пользователь не найден".

    Args:
        request (Request): объект FastAPI запроса
        tg_id (str, optional): Telegram ID пользователя из заголовка X-Telegram-Id.
            Получается через dependency `APIKeyHeader`.
        secret_key (str, optional): общий секрет bot/ <-> api/ из заголовка
            X-Internal-Secret.

    Returns
        User: модель пользователя, найденного в базе данных

    Raises
        InvalidInternalSecretError: если X-Internal-Secret отсутствует/неверен
        MissingTelegramHeaderError: если заголовок X-Telegram-Id отсутствует
        UserNotFoundError: если пользователь с указанным telegram_id не найден

    """
    expected_secret = settings_api.internal_api_secret.get_secret_value()

    if not secret_key or not secrets.compare_digest(secret_key, expected_secret):
        raise InvalidInternalSecretError()

    if not tg_id:
        raise MissingTelegramHeaderError()

    user: User | None = getattr(request.state, "user", None)

    if user is None:
        raise UserNotFoundError(tg_id=tg_id)

    return user
