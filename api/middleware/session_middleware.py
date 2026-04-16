from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from api.core.database import async_session


class DBSessionMiddleware(BaseHTTPMiddleware):
    """Middleware для предоставления асинхронной сессии базы данных на каждый запрос.

    Создаёт новую асинхронную сессию SQLAlchemy для каждого HTTP-запроса
    и сохраняет её в `request.state.db`. После завершения обработки запроса
    сессия автоматически закрывается.

    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Обрабатывает входящий запрос и внедряет DB-сессию.

        Args:
            request: Объект входящего HTTP-запроса FastAPI.
            call_next: Следующий обработчик в цепочке middleware.

        Returns
            Response: HTTP-ответ, сформированный обработчиками ниже по цепочке.

        """
        async with async_session() as session:
            request.state.db = session
            response: Response = await call_next(request)

        return response
