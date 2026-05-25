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
from api.core.exceptions.schema import ErrorEnvelope, ErrorDetail


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if exc.__cause__:
        logger.exception(
            "Исходное исключение exception: {}",
            repr(exc.__cause__),
        )
    if not isinstance(exc, APIError):
        logger.error("Непредвиденное исключение exception: %s", type(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code="internal_error",
                    message=f"Internal server error ({str(exc)})",
                    details={"exc_type": type(exc)},
                )
            ).model_dump(),
        )

    logger.warning(
        "APIError path={} code={} message={}",
        request.url.path,
        exc.code,
        exc.message,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_envelope().model_dump(),
    )


async def request_validation_handler(
    request: Request,
    exc: RequestValidationError,
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
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="database_error",
                message=f"Ошибка работы с базой данных {str(exc)}",
                details={"exc_type": type(exc).__name__},
            )
        ).model_dump(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Необработанное исключение при запросе %s", request.url.path)
    if exc.__cause__:
        logger.exception(
            "Исходное исключение exception: {}",
            repr(exc.__cause__),
        )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Внутрення ошибка сервера",
                "details": {"exc_type": type(exc).__name__},
            }
        },
    )
