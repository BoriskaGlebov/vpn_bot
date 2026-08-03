from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования входящих запросов и исходящих ответов."""

    def __init__(self, app: ASGIApp) -> None:
        """Инициализация middleware.

        Args:
            app: Экземпляр FastAPI приложения.

        """
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Логирует начало запроса и ответ.

        Args:
            request (Request): Входящий HTTP-запрос.
            call_next (Callable): Функция для вызова следующего обработчика запроса.

        Returns
            Response: Ответ клиенту.

        """
        # Логируется только path, не полный URL — query-параметры в будущем
        # могут содержать чувствительные значения (например, токены), которых
        # в логах быть не должно.
        logger.info(
            "Начало запроса: {method} {path} от {client}",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )

        response = await call_next(request)

        logger.info(
            "Завершен запрос: {method} {path} от {client} -> {status_code}",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
            status_code=response.status_code,
        )

        return response
