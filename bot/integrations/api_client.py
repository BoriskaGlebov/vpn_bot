import asyncio
import random
from collections.abc import Mapping
from typing import Any

import httpx
from loguru import logger

from bot.app_error.api_error import (
    APIClientConnectionError,
    APIClientHTTPError,
    APIClientInvalidJSONError,
    map_http_error,
)
from bot.app_error.schema import ErrorDetail
from shared.config.context import log_context


class APIClient:
    """Асинхронный HTTP клиент с retry, логированием и обработкой ошибок.

    Все методы (`get`/`post`/`patch`/`delete`) возвращают одну и ту же форму —
    `tuple[dict[str, Any], int]` (тело ответа и статус-код), а не вразнобой.

    Повтор запроса при сетевой ошибке или 5xx безопасен только тогда, когда сам
    запрос точно не повлиял на состояние сервера. `ConnectError` гарантирует
    это — соединение не установилось, запрос не ушёл. `ReadTimeout`/
    `WriteTimeout` и ответ 5xx такой гарантии не дают: запрос мог уйти и уже
    обработаться на сервере, не дождались только (корректного) ответа. Поэтому
    их повтор допускается только для идемпотентных методов
    (`_IDEMPOTENT_METHODS`) — для `POST`/`PATCH`/`DELETE` они поднимаются сразу,
    без повторной отправки. Задержка между попытками растёт экспоненциально
    и содержит джиттер, чтобы не синхронизировать повторы параллельных
    запросов в момент, когда `api/` и так не справляется с нагрузкой.

    Args:
        base_url (str): Базовый URL API.
        port (int): Порт API.
        timeout (float): Таймаут чтения/записи/пула запроса.
        connect_timeout (float): Таймаут установки соединения.
        max_retries (int): Количество попыток.
        retry_delay (float): Базовая задержка между попытками (основание для
            экспоненциального backoff).
        scheme (str): Схема подключения ("http"/"https").
        internal_secret (str | None): Секрет для заголовка X-Internal-Secret
            (только для клиента нашего api/).

    """

    _IDEMPOTENT_METHODS = frozenset({"GET"})
    _RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})

    def __init__(
        self,
        base_url: str,
        port: int,
        timeout: float = 5.0,
        connect_timeout: float = 2.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        scheme: str = "http",
        internal_secret: str | None = None,
    ) -> None:
        """Инициализация класса Клиента.

        Args:
            base_url: Хост целевого сервиса (со схемой или без — схема будет
                подставлена из аргумента `scheme`).
            port: Порт целевого сервиса.
            timeout: Таймаут чтения/записи/пула в секундах.
            connect_timeout: Таймаут установки соединения в секундах.
            max_retries: Количество попыток при неудачном запросе. Должно
                быть не меньше 1.
            retry_delay: Базовая задержка между повторными попытками в
                секундах (растёт экспоненциально с номером попытки).
            scheme: Схема подключения (`http`/`https`).
            internal_secret: Секрет для заголовка X-Internal-Secret. Задаётся
                только для клиента нашего api/ — сторонним хостам (например,
                панелям XRay) он передаваться не должен.

        Raises
            ValueError: Если `max_retries < 1`.

        """
        if max_retries < 1:
            raise ValueError("max_retries должен быть не меньше 1")

        base_url = base_url.rstrip("/")

        # если вдруг передали уже с http/https — убираем
        base_url = base_url.replace("http://", "").replace("https://", "")

        self.base_url = f"{scheme}://{base_url}:{port}"
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._internal_secret = internal_secret

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=self.connect_timeout,
                read=self.timeout,
                write=self.timeout,
                pool=self.timeout,
            ),
        )

    def _backoff_delay(self, attempt: int) -> float:
        """Экспоненциальная задержка с джиттером перед следующей попыткой.

        Args:
            attempt (int): Номер уже выполненной попытки (с 1).

        Returns
            float: Задержка в секундах.

        """
        base = self.retry_delay * (2 ** (attempt - 1))
        jitter = random.uniform(0, base * 0.25)
        return base + jitter

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        await self._client.aclose()

    def _build_headers(
        self, headers: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        result = dict(headers or {})

        if self._internal_secret:
            result["X-Internal-Secret"] = self._internal_secret

        ctx = log_context.get()

        if ctx is None:
            return result

        if ctx.tg_id is not None:
            result["X-Telegram-Id"] = str(ctx.tg_id)

        if ctx.username:
            result["X-Telegram-Username"] = ctx.username

        return result

    def _build_http_error(self, response: httpx.Response) -> APIClientHTTPError:
        """Строит ошибку HTTP из ответа, не теряя статус-код на не-JSON теле.

        Args:
            response (httpx.Response): Ответ сервера со статусом >= 400.

        Returns
            APIClientHTTPError: Ошибка с сохранённым статус-кодом — даже если
                тело ответа не JSON (например, HTML-страница от nginx при 502).

        """
        try:
            error_body = response.json()
        except ValueError:
            logger.error(
                "Невалидный JSON в ответе с ошибкой: {} {} {}",
                response.request.method,
                response.request.url,
                response.status_code,
            )
            return APIClientHTTPError(
                response.status_code,
                ErrorDetail(
                    code="invalid_json_response",
                    message=(
                        f"API вернул нераспознаваемое тело при статусе "
                        f"{response.status_code}"
                    ),
                ),
            )
        # Тело ответа может содержать чувствительные данные (эхо платёжных
        # реквизитов, паролей и т.п. от стороннего сервиса), поэтому в
        # постоянные логи (WARNING/ERROR) оно не попадает — только на DEBUG
        # и усечённым.
        logger.debug(
            "HTTP error body: {} {} -> {} | body={}",
            response.request.method,
            response.request.url,
            response.status_code,
            str(error_body)[:500],
        )
        return map_http_error(response.status_code, error_body)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Выполняет HTTP запрос с retry и логированием.

        Args:
            method (str): HTTP метод.
            url (str): URL endpoint.

        Raises
            APIClientHTTPError: Ошибка HTTP. Для 5xx на неидемпотентном
                методе поднимается сразу, без повтора — запрос мог уже
                обработаться на сервере.
            APIClientConnectionError: Ошибка соединения. Для `ReadTimeout`/
                `WriteTimeout` на неидемпотентном методе поднимается сразу,
                по той же причине.

        Returns
            httpx.Response: Ответ сервера.

        """
        last_exc: Exception | None = None
        is_idempotent = method.upper() in self._IDEMPOTENT_METHODS

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "HTTP запрос: {} {} (попытка {}/{})",
                    method,
                    url,
                    attempt,
                    self.max_retries,
                )
                raw_headers = kwargs.pop("headers", None)
                headers = self._build_headers(raw_headers)

                response = await self._client.request(
                    method=method, url=url, headers=headers, **kwargs
                )
                logger.debug(
                    "HTTP ответ: {} {} -> {}",
                    method,
                    url,
                    response.status_code,
                )
                if response.status_code >= 400:
                    logger.warning(
                        "HTTP error: {} {} -> {}",
                        method,
                        url,
                        response.status_code,
                    )
                    error = self._build_http_error(response)

                    retryable = response.status_code in self._RETRYABLE_STATUSES
                    if retryable and is_idempotent and attempt < self.max_retries:
                        last_exc = error
                        await asyncio.sleep(self._backoff_delay(attempt))
                        continue

                    raise error

                return response

            except httpx.ConnectError as exc:
                # Соединение не установилось — запрос гарантированно не ушёл,
                # повтор безопасен для любого метода.
                last_exc = exc
                logger.warning(
                    "Connection error: {} {} (попытка {}/{}): {}",
                    method,
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt == self.max_retries:
                    raise APIClientConnectionError() from exc

                await asyncio.sleep(self._backoff_delay(attempt))
            except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                if not is_idempotent:
                    # Запрос мог уже обработаться на сервере — повтор означал
                    # бы выполнить изменяющую операцию второй раз.
                    logger.error(
                        "Таймаут на неидемпотентном запросе, повтор пропущен: "
                        "{} {} (попытка {}/{}): {}",
                        method,
                        url,
                        attempt,
                        self.max_retries,
                        exc,
                    )
                    raise APIClientConnectionError() from exc

                last_exc = exc
                logger.warning(
                    "Connection error: {} {} (попытка {}/{}): {}",
                    method,
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt == self.max_retries:
                    raise APIClientConnectionError() from exc

                await asyncio.sleep(self._backoff_delay(attempt))
            except httpx.RequestError as exc:
                logger.error(
                    "Ошибка без повторного запрашивания request error: {} {}: {}",
                    method,
                    url,
                    exc,
                )
                raise APIClientConnectionError() from exc

        # Недостижимо: __init__ гарантирует max_retries >= 1, и внутри цикла
        # любой исход — либо return, либо raise. Оставлено для mypy и как
        # защита от будущих изменений цикла.
        raise APIClientConnectionError() from last_exc

    async def _parse_json(self, response: httpx.Response) -> dict[str, Any]:
        """Парсит JSON с обработкой ошибок."""
        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "Невалидный JSON ответ: {} {} {}",
                response.request.method,
                response.request.url,
                response.status_code,
            )
            raise APIClientInvalidJSONError() from exc
        return data

    async def get(self, url: str, **kwargs: Any) -> tuple[dict[str, Any], int]:
        """GET запрос."""
        response = await self._request("GET", url, **kwargs)
        return await self._parse_json(response), response.status_code

    async def post(self, url: str, **kwargs: Any) -> tuple[dict[str, Any], int]:
        """POST запрос."""
        response = await self._request("POST", url, **kwargs)
        return await self._parse_json(response), response.status_code

    async def patch(self, url: str, **kwargs: Any) -> tuple[dict[str, Any], int]:
        """PATCH запрос."""
        response = await self._request("PATCH", url, **kwargs)
        return await self._parse_json(response), response.status_code

    async def delete(self, url: str, **kwargs: Any) -> tuple[dict[str, Any], int]:
        """DELETE запрос."""
        response = await self._request("DELETE", url, **kwargs)
        return await self._parse_json(response), response.status_code
