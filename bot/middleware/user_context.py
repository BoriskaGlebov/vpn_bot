from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

from shared.config.context import LogUserContext, log_context


class UserContextMiddleware(BaseMiddleware):
    """Middleware для установки контекста пользователя в ContextVar.

    Извлекает пользователя из входящего события Telegram (Update) и
    сохраняет его данные в ``log_context`` (ContextVar), чтобы они были
    доступны в логировании и других слоях (например, HTTP-клиенте).

    Контекст автоматически сбрасывается после завершения обработки события,
    что предотвращает утечки данных между разными update.

    Поддерживаемые типы событий:
        - message
        - callback_query
        - inline_query

    Если пользователь не найден (например, системные события),
    обработка продолжается без установки контекста.

    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Обрабатывает входящее событие и устанавливает контекст пользователя.

        Args:
            handler: Следующий обработчик в цепочке middleware.
            event: Входящее событие Telegram (обычно Update).
            data: Дополнительные данные, передаваемые между middleware.

        Returns
            Any: Результат выполнения следующего обработчика.

        """
        user: User | None = None

        # Работаем только с Update
        if isinstance(event, Update):
            if event.message:
                user = event.message.from_user
            elif event.callback_query:
                user = event.callback_query.from_user
            elif event.inline_query:
                user = event.inline_query.from_user

        if user is not None:
            token = log_context.set(
                LogUserContext(
                    user=user.username or str(user.id),
                    tg_id=user.id,
                    username=user.username,
                )
            )

            try:
                return await handler(event, data)
            finally:
                log_context.reset(token)

        return await handler(event, data)
