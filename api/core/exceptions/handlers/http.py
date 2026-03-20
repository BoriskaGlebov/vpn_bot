from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette import status


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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Ошибка валидации запроса",
            "errors": exc.errors(),
        },
    )
