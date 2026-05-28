from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from api.app_error.base_error import (
    AppError,
)
from api.core.exceptions.schema import ErrorDetail, ErrorEnvelope


async def log_cause(exc: Exception) -> None:
    """Логирует исходное исключение через `__cause__`.

    Используется для сохранения цепочки ошибок при повторном
    выбрасывании исключений через конструкцию:

        raise NewError() from original_error

    Если исходное исключение отсутствует, логирование не выполняется.

    Args:
        exc: Текущее обрабатываемое исключение.

    """
    if exc.__cause__:
        logger.exception(
            "Исходное исключение exception: {}",
            repr(exc.__cause__),
        )


async def unexpected_exception_loger(exc: Exception) -> JSONResponse:
    """Обрабатывает непредвиденные исключения приложения.

    Логирует информацию о необработанном исключении и формирует
    унифицированный HTTP-ответ с кодом 500.

    В production-режиме не рекомендуется передавать текст
    исключения клиенту, так как это может привести к утечке
    внутренней информации приложения.

    Args:
        exc: Непредвиденное исключение.

    Returns
        JSONResponse: HTTP-ответ со статусом 500 и структурой ошибки.

    """
    logger.error(
        "Непредвиденное исключение exception: ({}) {}", type(exc).__name__, str(exc)
    )
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="internal_error",
                message=f"Internal server error ({str(exc)})",
                details={"exc_type": type(exc).__name__},
            )
        ).model_dump(),
    )


async def app_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Универсальный обработчик исключений приложения.

    Обрабатывает все исключения типа `AppError` и преобразует их
    в унифицированный JSON-ответ API.

    Если исключение не является наследником `AppError`,
    оно считается непредвиденным и передаётся в обработчик
    `unexpected_exception_logger`.

    Для серверных ошибок (`status_code >= 500`) используется
    уровень логирования `exception`, для клиентских —
    `warning`.

    Args:
        request: Текущий HTTP-запрос.
        exc: Обрабатываемое исключение.

    Returns
        JSONResponse: HTTP-ответ с сериализованной ошибкой API.

    """
    await log_cause(exc=exc)
    if not isinstance(exc, AppError):
        return await unexpected_exception_loger(exc=exc)

    if exc.status_code >= 500:
        logger.exception(
            "APIError {} path={} code={} message={} details={}",
            exc.__class__.__name__,
            request.url.path,
            exc.code,
            exc.message,
            exc.details,
        )
    else:
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
