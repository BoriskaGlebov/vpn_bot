import asyncio
from collections.abc import Mapping
from typing import Any

import httpx
from loguru import logger

from bot.app_error.api_error import (
    APIClientConnectionError,
    APIClientError,
    map_http_error,
)
from shared.config.context import log_context


class APIClient:
    """Асинхронный HTTP клиент с retry, логированием и обработкой ошибок.

    Args:
        base_url (str): Базовый URL API.
        timeout (float): Таймаут запроса.
        max_retries (int): Количество попыток.
        retry_delay (float): Задержка между попытками.

    """

    def __init__(
        self,
        base_url: str,
        port: int,
        timeout: float = 5.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> None:
        """Инициализация класса Клиента."""
        self.base_url = f"https://{base_url.rstrip('/')}:{port}"
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=2.0, read=self.timeout, write=self.timeout, pool=self.timeout
            ),
        )

    async def close(self) -> None:
        """Закрывает HTTP клиент."""
        await self._client.aclose()

    def _build_headers(
        self, headers: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        result = dict(headers or {})

        ctx = log_context.get()

        if ctx is None:
            return result

        if ctx.tg_id is not None:
            result["X-Telegram-Id"] = str(ctx.tg_id)

        if ctx.username:
            result["X-Telegram-Username"] = ctx.username

        return result

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
            APIClientHTTPError: Ошибка HTTP.
            APIClientConnectionError: Ошибка соединения.

        Returns
            httpx.Response: Ответ сервера.

        """
        last_exc: Exception | None = None

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
                        "HTTP error: {} {} -> {} | body={}",
                        method,
                        url,
                        response.status_code,
                        response.text,
                    )
                    raise map_http_error(response.status_code, response.text)

                return response

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
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
                    raise APIClientConnectionError(
                        "Не удалось подключиться к API",
                        cause=exc,
                    ) from exc

                await asyncio.sleep(self.retry_delay)
            except httpx.RequestError as exc:
                logger.error(
                    "Ошибка без повторного запрашивания request error: {} {}: {}",
                    method,
                    url,
                    exc,
                )
                raise APIClientConnectionError(
                    "Ошибка запроса",
                    cause=exc,
                ) from exc
        raise APIClientError("Неизвестная ошибка", cause=last_exc)

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
            raise APIClientError(
                "Ответ API не является корректным JSON",
                cause=exc,
            ) from exc
        return data

    async def get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """GET запрос."""
        response = await self._request("GET", url, **kwargs)
        return await self._parse_json(response)

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
