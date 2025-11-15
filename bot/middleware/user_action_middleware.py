from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru._logger import Logger

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UserActionLoggingMiddleware(BaseMiddleware):  # type: ignore[misc]
    """Middleware для логирования действий пользователя в хэндлерах.

    Логирует:
        - Начало и конец выполнения обработчика.
        - Идентификатор пользователя (username или id).
        - Время выполнения обработчика.
        - Содержимое события (опционально).

    Attributes
        log_data (bool): Логировать данные события.
        log_time (bool): Логировать время выполнения хэндлера.
        logger (Logger): Экземплар класса логгера для логирования.

    """

    def __init__(
        self, logger: Logger, log_data: bool = False, log_time: bool = True
    ) -> None:
        super().__init__()
        self.log_data = log_data
        self.log_time = log_time
        self.logger = logger

    @staticmethod
    def _get_user_identifier(event: TelegramObject) -> str | int | None:
        """Возвращает username или id пользователя."""
        user = getattr(event, "from_user", None)
        if not user:
            return None

        username = user.username
        if isinstance(username, str):
            return username

        user_id = getattr(user, "id", None)
        return cast(str | int | None, user_id)

    @staticmethod
    def _get_event_type(event: TelegramObject) -> str:
        """Возвращает короткое имя события."""
        return type(event).__name__

    def _log_start(
        self, user: str | int | None, event_type: str, event: TelegramObject
    ) -> None:
        """Логирует начало обработки."""
        if self.log_data:
            self.logger.bind(user=user).info(f"START {event_type}: {event!r}")
        else:
            self.logger.bind(user=user).info(f"START {event_type}")

    def _log_end(
        self,
        user: str | int | None,
        event_type: str,
        start_time: float,
        event: TelegramObject,
    ) -> None:
        """Логирует окончание обработки."""
        if self.log_time:
            duration = time.time() - start_time
            if self.log_data:
                self.logger.bind(user=user).info(
                    f"END {event_type} ({duration:.3f}s): {event!r}"
                )
            else:
                self.logger.bind(user=user).info(f"END {event_type} ({duration:.3f}s)")
        else:
            if self.log_data:
                self.logger.bind(user=user).info(f"END {event_type}: {event!r}")
            else:
                self.logger.bind(user=user).info(f"END {event_type}")

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Оборачивает вызов обработчика для логирования.

        Args:
            handler (Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]):
                Функция-обработчик события.
            event (TelegramObject): Событие от Telegram.
            data (dict[str, Any]): Словарь с дополнительными данными.

        Returns
            Any: Результат выполнения обработчика.

        """
        user = self._get_user_identifier(event)
        event_type = self._get_event_type(event)

        self._log_start(user, event_type, event)
        start_time = time.time()

        try:
            return await handler(event, data)
        finally:
            self._log_end(user, event_type, start_time, event)
