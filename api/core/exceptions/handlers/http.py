from typing import cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from starlette import status

from api.app_error.api_error import (
    AdminNotFoundHeaderError,
    MissingTelegramHeaderError,
    UserNotFoundHeaderError,
)


async def request_validation_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обрабатывает ошибки валидации входящего HTTP запроса.

    Перехватывает ошибки FastAPI валидации (Pydantic / query / body)
    и приводит их к единому формату API ответа.

    Args:
        request (Request): HTTP запрос FastAPI.
        exc (RequestValidationError): Ошибка валидации запроса.

    Returns
        JSONResponse: HTTP 422 ответ с деталями ошибок.

    """
    exc = cast(RequestValidationError, exc)
    logger.warning(
        "RequestValidationError path={} errors={}",
        request.url.path,
        exc.errors(),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": "Ошибка валидации запроса",
            "errors": exc.errors(),
        },
    )


async def database_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обрабатывает ошибки базы данных и возвращает HTTP-ответ.

    Хендлер предназначен для перехвата всех исключений, связанных с работой
    с базой данных (SQLAlchemy), логирования ошибки и возврата безопасного
    ответа клиенту без раскрытия внутренних деталей.

    Args:
        request (Request): Объект входящего HTTP-запроса.
        exc (SQLAlchemyError): Исключение, возникшее при работе с БД.

    Returns
        JSONResponse: HTTP-ответ с кодом 500 и обобщённым сообщением об ошибке.

    HTTP статус-коды:
        500: Внутренняя ошибка сервера (ошибка БД)

    """
    exc = cast(SQLAlchemyError, exc)
    logger.error(
        "DatabaseException path={} error={}",
        request.url.path,
        str(exc),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Ошибка работы с базой данных",
        },
    )


async def missing_telegram_header_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обрабатывает отсутствие заголовка X-Telegram-Id."""
    exc = cast(MissingTelegramHeaderError, exc)

    logger.warning(
        "MissingTelegramHeaderError: path={} header={}",
        request.url.path,
        exc.header_name,
    )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "detail": str(exc),
            "error": "missing_telegram_header",
        },
    )


async def unregistered_user_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обрабатывает незарегистрированного пользователя."""
    exc = cast(UserNotFoundHeaderError, exc)

    logger.warning(
        "MissingTelegramHeaderError: path={} header={}",
        request.url.path,
        exc.tg_id,
    )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "detail": str(exc),
            "error": "unregistered_user_handler",
        },
    )


async def user_not_admin_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обрабатывает запрос от не админа."""
    exc = cast(AdminNotFoundHeaderError, exc)

    logger.warning(
        "MissingTelegramHeaderError: path={} header={}",
        request.url.path,
        exc.tg_id,
    )

    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "detail": str(exc),
            "error": "user_not_admin_handler",
        },
    )
