from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import (
    RestartingTelegram,
    TelegramAPIError,
    TelegramBadRequest,
    TelegramConflictError,
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import logger, settings_bot


class ErrorHandlerMiddleware(BaseMiddleware):  # type: ignore[misc]
    """Промежуточное ПО для обработки исключений в aiogram.

    Ловит типовые ошибки Telegram API, отправляет пользователю
    дружелюбные сообщения и логирует полные трассировки ошибок.

    Methods
        __call__(handler, event, data):
            Обрабатывает событие, перехватывает исключения и логирует их.

    Args:
        handler (Callable[[Any, Dict[str, Any]], Awaitable[Any]]):
            Оригинальный хендлер события.
        event (Union[types.Message, types.CallbackQuery, Any]):
            Событие Telegram, которое передаётся хендлеру.
        data (Dict[str, Any]):
            Контекстные данные для хендлера.

    Raises
        Все необработанные исключения логируются и, если возможно,
        пользователю отправляется уведомление о проблеме.

    """

    def __init__(self) -> None:
        super().__init__()
        self.error_messages: dict[type[Exception], str] = {
            TelegramRetryAfter: "⚠️ Слишком много запросов. Попробуйте позже.",
            TelegramForbiddenError: "⚠️ Доступ запрещён. Возможно, бот был удалён или заблокирован.",
            TelegramUnauthorizedError: "⚠️ Неверный токен бота.",
            TelegramNotFound: "⚠️ Не удалось найти чат или сообщение.",
            TelegramBadRequest: "⚠️ Неверный запрос.",
            TelegramEntityTooLarge: "⚠️ Файл слишком большой для отправки.",
            TelegramNetworkError: "⚠️ Проблемы на стороне Telegram. Попробуйте позже.",
            TelegramServerError: "⚠️ Проблемы на стороне Telegram. Попробуйте позже.",
            RestartingTelegram: "⚠️ Проблемы на стороне Telegram. Попробуйте позже.",
            TelegramMigrateToChat: "⚠️ Чат был перемещен. Попробуйте повторно.",
            TelegramConflictError: "⚠️ Конфликт токена бота. Попробуйте позже.",
            TelegramAPIError: "⚠️ Ошибка Telegram API. Попробуйте повторить действие.",
        }

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Перехватывает исключения, возникающие при обработке событий и логирует их."""
        try:
            return await handler(event, data)

        except Exception as exception:
            user_id: int | None = None
            if isinstance(event, Message) and event.from_user is not None:
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery) and event.from_user is not None:
                user_id = event.from_user.id

            user_message = settings_bot.MESSAGES.get("general", {}).get(
                "common_error", "⚠️ Произошла ошибка. Попробуйте позже."
            )

            for exc_type, message in self.error_messages.items():
                if isinstance(exception, exc_type):
                    if isinstance(exception, TelegramRetryAfter):
                        user_message = f"⚠️ Слишком много запросов. Попробуйте через {exception.retry_after} секунд."
                    elif isinstance(exception, TelegramBadRequest):
                        user_message = f"⚠️ Неверный запрос: {exception.message}"
                    else:
                        user_message = message
                    break

            try:
                if isinstance(event, Message):
                    await event.reply(user_message)
                elif isinstance(event, CallbackQuery) and event.message is not None:
                    await event.message.answer(user_message)
            except Exception:
                logger.exception("Не удалось отправить сообщение пользователю")

            update_id = getattr(event, "update_id", None)
            logger.bind(user=user_id).exception(
                "Ошибка при обработке update. user_id=%s, update_id=%s",
                user_id,
                update_id,
            )
