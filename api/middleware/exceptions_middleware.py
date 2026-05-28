import traceback
from collections.abc import Awaitable, Callable

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from api.core.exceptions.handlers.business import unexpected_exception_loger


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования непредвиденных ошибок.

    Этот middleware оборачивает все HTTP-запросы и логирует
    исключения, которые не были обработаны кастомными
    exception handler'ами. В случае возникновения ошибки
    возвращает статус 500.

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
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.exception(
                f"[ExceptionLoggingMiddleware] Неожиданная ошибка: {e}\n{tb_str}"
            )
            return await unexpected_exception_loger(exc=e)
