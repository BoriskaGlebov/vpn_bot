from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования входящих запросов и исходящих ответов."""

    def __init__(self, app: FastAPI) -> None:
        """Инициализация middleware.

        Args:
            app: Экземпляр FastAPI приложения.

        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Логирует начало запроса и ответ.

        Args:
            request (Request): Входящий HTTP-запрос.
            call_next (Callable): Функция для вызова следующего обработчика запроса.

        Returns
            Response: Ответ клиенту.

        """
        logger.info(
            "Начало запроса: {method} {url} от {client}",
            method=request.method,
            url=str(request.url),
            client=request.client.host if request.client else "unknown",
        )

        response = await call_next(request)

        logger.info(
            "Завершен запрос: {method} {url} от {client} -> {status_code}",
            method=request.method,
            url=str(request.url),
            client=request.client.host if request.client else "unknown",
            status_code=response.status_code,
        )

        return response
