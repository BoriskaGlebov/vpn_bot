from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware, Bot
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
from loguru._logger import Logger

from bot.app_error.base_error import UserNotFoundError, VPNLimitError
from bot.config import settings_bot

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


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

    def __init__(self, logger: Logger, bot: Bot) -> None:
        super().__init__()
        self.logger = logger
        self.bot = bot

        self.error_messages: dict[type[Exception], str] = {
            TelegramRetryAfter: "⚠️ Слишком много запросов.",
            TelegramForbiddenError: "⚠️ Доступ запрещён.",
            TelegramUnauthorizedError: "⚠️ Ошибка авторизации.",
            TelegramNotFound: "⚠️ Объект не найден.",
            TelegramBadRequest: "⚠️ Неверный запрос.",
            TelegramEntityTooLarge: "⚠️ Файл слишком большой.",
            TelegramNetworkError: "⚠️ Ошибка сети Telegram.",
            TelegramServerError: "⚠️ Ошибка сервера Telegram.",
            RestartingTelegram: "⚠️ Telegram временно недоступен.",
            TelegramMigrateToChat: "⚠️ Чат был перемещён.",
            TelegramConflictError: "⚠️ Конфликт токена.",
            TelegramAPIError: "⚠️ Ошибка Telegram API.",
        }

        self.default_user_message = cast(
            str,
            settings_bot.MESSAGES.get("general", {}).get(
                "common_error", "⚠️ Произошла ошибка. Попробуйте позже."
            ),
        )

    def _resolve_user_message(self, exc: Exception) -> str:
        """Универсальный метод получения сообщения для пользователя."""
        if isinstance(exc, VPNLimitError):
            return f"⚠️ Пользователь достиг лимита конфигов ({exc.limit})."
        if isinstance(exc, UserNotFoundError):
            return "⚠️ Пользователь не найден."
        for exc_type, message in self.error_messages.items():
            if isinstance(exc, exc_type):
                if isinstance(exc, TelegramRetryAfter):
                    return f"⚠️ Слишком много запросов. Попробуйте через {exc.retry_after} секунд."
                if isinstance(exc, TelegramBadRequest):
                    return f"⚠️ Неверный запрос: {exc.message}"

                return message
        return self.default_user_message

    async def _safe_send_error(self, event: TelegramObject, text: str) -> None:
        """Универсальная отправка сообщения пользователю."""
        try:
            if isinstance(event, Message):
                await event.reply(text)
            elif isinstance(event, CallbackQuery) and event.message:
                await event.message.answer(text)
        except Exception:
            self.logger.warning("Не удалось отправить ошибку пользователю")

    async def _notify_admins(self, event: TelegramObject, exc: Exception) -> None:
        """Отправляет сообщение админам с подробной информацией об ошибке."""
        try:
            user = getattr(event, "from_user", None)
            user_info = (
                f"{user.username} ({user.id})" if user else "Неизвестный пользователь"
            )
            update_id = getattr(event, "update_id", None)
            exc_type = type(exc).__name__
            exc_text = str(exc)

            msg = (
                f"⚠️ Ошибка у пользователя {user_info}\n"
                f"update_id: {update_id}\n"
                f"type: {exc_type}\n"
                f"message: {exc_text}"
            )
            for admin_id in settings_bot.ADMIN_IDS:
                await self.bot.send_message(chat_id=admin_id, text=msg)
        except Exception:
            self.logger.warning("Не удалось отправить сообщение админам")

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Перехватывает исключения, возникающие при обработке событий и логирует их."""
        try:
            return await handler(event, data)

        except Exception as exc:
            user_id: int | None = None
            user = getattr(event, "from_user", None)

            if user is not None:
                user_id = getattr(user, "id", None)

            user_message = self._resolve_user_message(exc)
            await self._safe_send_error(event, user_message)
            await self._notify_admins(event, exc)
            update_id = getattr(event, "update_id", None)
            exception_type = type(exc).__name__
            self.logger.bind(
                user=user_id,
            ).exception(
                f"[update_id] - {update_id}\n"
                f"[exception_type]{exception_type}\n"
                f"Ошибка при обработке обновления"
            )

            return None
