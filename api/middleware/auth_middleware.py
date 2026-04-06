from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.users.dao import UserDAO
from api.users.schemas import SUserTelegramID


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для аутентификации пользователя по заголовкам запроса.

    Извлекает Telegram ID пользователя из заголовка ``X-Telegram-Id``,
    выполняет поиск пользователя в базе данных и сохраняет результат
    в ``request.state.user``.

    Ожидаемые заголовки:
        - X-Telegram-Id (str): Telegram ID пользователя
        - X-Telegram-Username (str, optional): Username пользователя

    Требования:
        - Middleware работы с БД (устанавливающий ``request.state.db``)
          должен быть подключён ранее.

    Если заголовок ``X-Telegram-Id`` отсутствует или некорректен,
    пользователь не будет найден, и ``request.state.user`` останется ``None``.

    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Обрабатывает HTTP-запрос и устанавливает пользователя в контекст.

        Args:
            request (Request): Входящий HTTP-запрос.
            call_next (Callable): Следующий middleware или endpoint.

        Returns
            Response: HTTP-ответ.

        """
        tg_id = request.headers.get("X-Telegram-Id")
        # username = request.headers.get("X-Telegram-Username")

        tg_id_int: int | None = None

        if tg_id is not None:
            try:
                tg_id_int = int(tg_id)
            except ValueError:
                tg_id_int = None

        user = None

        if tg_id_int is not None:
            user = await UserDAO.find_one_or_none(
                session=request.state.db,
                filters=SUserTelegramID(telegram_id=tg_id_int),
                options=UserDAO.base_options,
            )

        request.state.user = user

        return await call_next(request)
