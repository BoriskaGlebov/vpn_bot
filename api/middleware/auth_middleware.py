import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from api.core.config import settings_api
from api.users.dao import UserDAO
from api.users.schemas import SUserTelegramID


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для аутентификации пользователя по заголовкам запроса.

    Извлекает Telegram ID пользователя из заголовка ``X-Telegram-Id``,
    выполняет поиск пользователя в базе данных и сохраняет результат
    в ``request.state.user``.

    Заголовок ``X-Telegram-Id`` сам по себе ничего не подтверждает — его
    может прислать кто угодно. Поэтому запрос дополнительно должен нести
    заголовок ``X-Internal-Secret``, совпадающий с ``settings_api.internal_api_secret``
    (его проставляет только наш bot/, см. ``bot/integrations/api_client.py``).
    Без верного секрета ``X-Telegram-Id`` игнорируется.

    Ожидаемые заголовки:
        - X-Internal-Secret (str): общий секрет bot/ <-> api/
        - X-Telegram-Id (str): Telegram ID пользователя
        - X-Telegram-Username (str, optional): Username пользователя

    Требования:
        - Middleware работы с БД (устанавливающий ``request.state.db``)
          должен быть подключён ранее.

    Если секрет неверный/отсутствует, либо заголовок ``X-Telegram-Id``
    отсутствует или некорректен, пользователь не будет найден, и
    ``request.state.user`` останется ``None``.

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
        internal_secret = request.headers.get("X-Internal-Secret", "")
        expected_secret = settings_api.internal_api_secret.get_secret_value()

        if not secrets.compare_digest(internal_secret, expected_secret):
            if internal_secret:
                # Секрет присутствует, но не совпадает — это подозрительно
                # (кто-то подобрал/подделал заголовок), в отличие от полного
                # отсутствия секрета, что нормально для не-bot трафика
                # (браузер на /docs, SQLAdmin, health-check и т.п.) — иначе
                # WARNING сыпался бы в error.log на каждый такой запрос.
                logger.warning(
                    "[AuthMiddleware]: неверный X-Internal-Secret path={}",
                    request.url.path,
                )
            else:
                logger.debug(
                    "[AuthMiddleware]: запрос без X-Internal-Secret path={}",
                    request.url.path,
                )
            request.state.user = None
            return await call_next(request)

        tg_id_raw = request.headers.get("X-Telegram-Id")
        # `log_context` (ContextVar) выставляется `LogContextMiddleware`,
        # который по построению цепочки middleware выполняется уже ПОСЛЕ
        # этого — поэтому здесь `{extra[user]}` ещё не заполнен автоматически
        # и нужно явно привязывать известный на этот момент tg_id.
        log = logger.bind(user=tg_id_raw or "-")

        log.debug("[AuthMiddleware]: path={} tg_id_raw={}", request.url.path, tg_id_raw)

        tg_id_int: int | None = None

        if tg_id_raw is not None:
            try:
                tg_id_int = int(tg_id_raw)
            except ValueError:
                log.warning(
                    "[AuthMiddleware]: некорректный tg_id path={} tg_id_raw={}",
                    request.url.path,
                    tg_id_raw,
                )
                tg_id_int = None

        user = None

        if tg_id_int is not None:
            user = await UserDAO.find_one_or_none(
                session=request.state.db,
                filters=SUserTelegramID(telegram_id=tg_id_int),
                options=UserDAO.base_options,
            )

            if user is None:
                log.info(
                    "[AuthMiddleware]: пользователь не найден path={} tg_id={}",
                    request.url.path,
                    tg_id_int,
                )
            else:
                log.debug(
                    "[AuthMiddleware]: пользователь найден path={} user_id={} tg_id={}",
                    request.url.path,
                    getattr(user, "id", None),
                    tg_id_int,
                )
        else:
            log.debug(
                "[AuthMiddleware]: tg_id отсутствует или невалиден path={}",
                request.url.path,
            )

        request.state.user = user

        response = await call_next(request)

        return response
