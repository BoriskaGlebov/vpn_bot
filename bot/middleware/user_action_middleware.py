import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger


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

    """

    def __init__(self, log_data: bool = True, log_time: bool = True) -> None:
        """Настройка логирования действий пользователя.

        Args:
            log_data (bool): логировать данные события (сообщение, callback)
            log_time (bool): логировать время выполнения хэндлера

        """
        super().__init__()
        self.log_data = log_data
        self.log_time = log_time

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
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
        user_identifier = None
        if hasattr(event, "from_user") and event.from_user:
            user_identifier = event.from_user.username or event.from_user.id

        event_type = type(event).__name__

        if self.log_data:
            logger.bind(user=user_identifier).info(
                f"START event_type={event_type}, event={event}"
            )
        else:
            logger.bind(user=user_identifier).info(f"START event_type={event_type}")

        start_time = time.time()
        try:
            result = await handler(event, data)
        finally:
            elapsed = time.time() - start_time
            if self.log_time:
                if self.log_data:
                    logger.bind(user=user_identifier).info(
                        f"END event_type={event_type}, длительность={elapsed:.3f}s, event={event}"
                    )
                else:
                    logger.bind(user=user_identifier).info(
                        f"END event_type={event_type}, длительность={elapsed:.3f}s"
                    )
            else:
                if self.log_data:
                    logger.bind(user=user_identifier).info(
                        f"END event_type={event_type}, event={event}"
                    )
                else:
                    logger.bind(user=user_identifier).info(
                        f"END event_type={event_type}"
                    )

        return result
