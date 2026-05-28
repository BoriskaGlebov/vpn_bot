from typing import cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from starlette import status

from api.app_error.api_error import (
    APIError,
)
from api.core.exceptions.handlers.business import log_cause, unexpected_exception_loger
from api.core.exceptions.schema import ErrorDetail, ErrorEnvelope


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обрабатывает пользовательские API-исключения приложения.

    Хендлер предназначен для обработки всех исключений,
    наследующихся от `APIError`, и преобразования их
    в унифицированный JSON-ответ API.

    Если исключение не относится к типу `APIError`,
    управление передаётся в обработчик непредвиденных ошибок.

    Args:
        request: Текущий HTTP-запрос.
        exc: Обрабатываемое исключение.

    Returns
        JSONResponse: HTTP-ответ с сериализованной ошибкой API.

    """
    await log_cause(exc=exc)
    if not isinstance(exc, APIError):
        return await unexpected_exception_loger(exc=exc)

    logger.warning(
        "APIError {} path={} code={} message={} details={}",
        exc.__class__.__name__,
        request.url.path,
        exc.code,
        exc.message,
        exc.details,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_envelope().model_dump(),
    )


async def request_validation_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Обрабатывает ошибки валидации HTTP-запросов.

    Перехватывает ошибки валидации FastAPI / Pydantic,
    возникающие при обработке query-параметров, path-параметров,
    заголовков и тела запроса.

    Все ошибки приводятся к единому формату API-ответа.

    Args:
        request: Текущий HTTP-запрос.
        exc: Исключение ошибки валидации FastAPI.

    Returns
        JSONResponse: HTTP-ответ со статусом 422 и деталями ошибки.

    """
    logger.warning(
        "RequestValidationError path={} errors={}",
        request.url.path,
        exc.errors(),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="validation_error",
                message=f"Ошибка валидации запроса {repr(exc)}",
                details={"exc_type": type(exc).__name__, "errors": exc.errors()},
            )
        ).model_dump(),
    )


async def database_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обрабатывает ошибки работы с базой данных.

    Перехватывает исключения SQLAlchemy, логирует информацию
    об ошибке и возвращает безопасный HTTP-ответ без раскрытия
    внутренних деталей реализации базы данных.

    Args:
        request: Текущий HTTP-запрос.
        exc: Исключение, связанное с базой данных.

    Returns
        JSONResponse: HTTP-ответ со статусом 500.

    """
    exc = cast(SQLAlchemyError, exc)
    logger.error(
        "DatabaseException path={} error={}",
        request.url.path,
        str(exc),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="database_error",
                message=f"Ошибка работы с базой данных {str(exc)}",
                details={"exc_type": type(exc).__name__},
            )
        ).model_dump(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обрабатывает все необработанные исключения приложения.

    Используется как fallback-хендлер для исключений,
    которые не были обработаны специализированными
    exception handlers.

    Логирует traceback и возвращает унифицированный
    HTTP-ответ с кодом 500.

    Args:
        request: Текущий HTTP-запрос.
        exc: Необработанное исключение.

    Returns
        JSONResponse: HTTP-ответ со статусом 500.

    """
    logger.exception("Необработанное исключение при запросе {}", request.url.path)
    await log_cause(exc=exc)
    return await unexpected_exception_loger(exc=exc)
