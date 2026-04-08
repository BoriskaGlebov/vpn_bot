from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from loguru import logger
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
        tg_id_raw = request.headers.get("X-Telegram-Id")

        logger.debug(
            "[AuthMiddleware]: path={} tg_id_raw={}",
            request.url.path,
            tg_id_raw,
        )

        tg_id_int: int | None = None

        if tg_id_raw is not None:
            try:
                tg_id_int = int(tg_id_raw)
            except ValueError:
                logger.warning(
                    "[AuthMiddleware]: некорректный tg_id path={} tg_id_raw={}",
                    request.url.path,
                    tg_id_raw,
                )
                tg_id_int = None

        user = None

        if tg_id_int is not None:
            logger.debug(
                "[AuthMiddleware]: поиск пользователя path={} tg_id={}",
                request.url.path,
                tg_id_int,
            )

            user = await UserDAO.find_one_or_none(
                session=request.state.db,
                filters=SUserTelegramID(telegram_id=tg_id_int),
                options=UserDAO.base_options,
            )

            if user is None:
                logger.info(
                    "[AuthMiddleware]: пользователь не найден path={} tg_id={}",
                    request.url.path,
                    tg_id_int,
                )
            else:
                logger.debug(
                    "[AuthMiddleware]: пользователь найден path={} user_id={} tg_id={}",
                    request.url.path,
                    getattr(user, "id", None),
                    tg_id_int,
                )
        else:
            logger.debug(
                "[AuthMiddleware]: tg_id отсутствует или невалиден path={}",
                request.url.path,
            )

        request.state.user = user

        response = await call_next(request)

        return response
