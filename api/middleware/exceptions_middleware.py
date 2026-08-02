from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from api.core.exceptions.handlers.business import unexpected_exception_logger


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    """Ловит исключения, не перехваченные `add_exception_handler`.

    `add_exception_handler(Exception, ...)` (см. `unhandled_exception_handler`)
    перехватывает исключения только из самого роутера — этот middleware
    добавлен как последний (а значит, самый внешний, см. порядок
    `add_middleware` в `api/main.py`), чтобы подстраховать и исключения,
    возникшие в других middleware (Auth/DBSession/RequestLogging/LogContext).
    В случае ошибки возвращает статус 500.

    Attributes
        app: Приложение FastAPI, к которому применяется middleware.

    """

    def __init__(self, app: ASGIApp) -> None:
        """Инициализирует middleware.

        Args:
            app: Экземпляр FastAPI приложения.

        """
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Обрабатывает HTTP-запрос, логируя необработанные исключения.

        Args:
            request (Request): Входящий HTTP-запрос.
            call_next (Callable): Функция для вызова следующего обработчика
                запроса в цепочке middleware.

        Returns
            JSONResponse: Ответ клиенту. В случае ошибки возвращает
            {"detail": "Internal server error"} с HTTP статусом 500.

        """
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            return await unexpected_exception_logger(exc=e, path=request.url.path)
