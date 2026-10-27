"""Единый формат ошибок HTTP-эндпоинтов бота (`ErrorEnvelope`), как в `api/`.

Зеркало `api/core/exceptions/handlers/` — без него `/webhook`, `/payment-webhook`
и `/internal/*` отдавали бы ошибки в разных форматах (дефолтный Starlette
`{"detail": ...}` для `HTTPException`, пустое тело для ручных `Response(...)`),
а не в едином `{"error": {"code", "message", "details"}}`.
"""

from collections.abc import Sequence

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

from bot.app_error.base_error import AppError
from bot.app_error.schema import ErrorDetail, ErrorEnvelope


def _sanitize_validation_errors(
    errors: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    """Убирает из ошибок pydantic то, что не предназначено для клиента.

    Зеркало одноимённой функции в `api/core/exceptions/handlers/http.py`:
    `exc.errors()` включает `input` (присланное клиентом значение — может
    быть секретом) и `url` (ссылка на документацию pydantic с версией).

    Args:
        errors: Результат `RequestValidationError.errors()`.

    Returns
        list[dict[str, object]]: Та же структура без `input`/`url`.

    """
    return [
        {k: v for k, v in error.items() if k in ("type", "loc", "msg")}
        for error in errors
    ]


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обрабатывает `AppError` на HTTP-эндпоинтах бота.

    Args:
        request: Текущий HTTP-запрос.
        exc: Обрабатываемое исключение.

    Returns
        JSONResponse: Ответ в формате `ErrorEnvelope` с кодом из `exc.status_code`.

    """
    if not isinstance(exc, AppError):
        return await unhandled_exception_handler(request, exc)

    log = logger.exception if exc.status_code >= 500 else logger.warning
    log(
        "AppError {} path={} code={} message={} details={}",
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


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Обрабатывает `HTTPException`, поднятые Starlette/FastAPI или кодом бота.

    Без этого хендлера такие ответы (например, 401/403 из
    `bot/internal/dependencies.py`) возвращались бы в формате Starlette
    по умолчанию (`{"detail": "..."}`), а не в едином `ErrorEnvelope`.

    Args:
        request: Текущий HTTP-запрос.
        exc: HTTPException.

    Returns
        JSONResponse: Ответ с тем же статус-кодом в формате `ErrorEnvelope`.

    """
    logger.warning(
        "HTTPException path={} status_code={} detail={}",
        request.url.path,
        exc.status_code,
        exc.detail,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="http_exception",
                message=str(exc.detail),
                details={"status_code": exc.status_code},
            )
        ).model_dump(),
        headers=exc.headers,
    )


async def request_validation_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Обрабатывает ошибки валидации тела/параметров запроса.

    Args:
        request: Текущий HTTP-запрос.
        exc: Исключение ошибки валидации FastAPI.

    Returns
        JSONResponse: Ответ со статусом 422 в формате `ErrorEnvelope`.

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
                message="Ошибка валидации запроса",
                details={"errors": _sanitize_validation_errors(exc.errors())},
            )
        ).model_dump(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback-обработчик для непредвиденных исключений.

    Текст исключения клиенту не передаётся (может содержать внутренние
    детали) — он доступен только в логах через `logger.exception`.

    Args:
        request: Текущий HTTP-запрос.
        exc: Необработанное исключение.

    Returns
        JSONResponse: Ответ со статусом 500 в формате `ErrorEnvelope`.

    """
    logger.exception(
        "Непредвиденное исключение: ({}) path={}",
        type(exc).__name__,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="internal_error",
                message="Internal server error",
                details={"exc_type": type(exc).__name__},
            )
        ).model_dump(),
    )
