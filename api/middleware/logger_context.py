from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.config.context import LogUserContext, log_context


class LogContextMiddleware(BaseHTTPMiddleware):
    """Middleware для установки пользовательского контекста логирования.

    Извлекает пользователя из ``request.state.user`` (если он был установлен
    предыдущими middleware, например AuthMiddleware) и сохраняет данные
    в ``log_context`` (ContextVar).

    Контекст используется для обогащения логов (через loguru patcher)
    и доступен на протяжении всего жизненного цикла HTTP-запроса.

    После завершения обработки запроса контекст автоматически сбрасывается.

    Ожидается, что ``request.state.user`` имеет атрибуты:
        - telegram_id (int | None)
        - username (str | None)

    Если пользователь отсутствует, контекст будет установлен с пустыми значениями.

    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Обрабатывает HTTP-запрос и устанавливает лог-контекст.

        Args:
            request (Request): Входящий HTTP-запрос.
            call_next (Callable): Следующий middleware или endpoint.

        Returns
            Response: HTTP-ответ.

        """
        user = getattr(request.state, "user", None)

        ctx = LogUserContext(
            user=getattr(user, "username", None)
            or (str(getattr(user, "telegram_id", None)) if user else None),
            tg_id=getattr(user, "telegram_id", None),
            username=getattr(user, "username", None),
        )

        token = log_context.set(ctx)

        try:
            response = await call_next(request)
        finally:
            log_context.reset(token)

        return response
