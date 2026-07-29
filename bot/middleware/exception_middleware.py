from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

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
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from loguru._logger import Logger

from bot.app_error.api_error import (
    APIClientError,
)
from bot.app_error.base_error import AppError
from bot.app_error.schema import ErrorDetail, ErrorEnvelope
from bot.core.config import settings_bot
from bot.utils.formatting import format_username
from bot.utils.start_stop_bot import send_to_admins

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ErrorHandlerMiddleware(BaseMiddleware):  # type: ignore[misc]
    """Перехватывает исключения хендлеров, нормализует их и уведомляет админов."""

    def __init__(self, logger: Logger, bot: Bot) -> None:
        super().__init__()
        self.logger = logger
        self.bot = bot

    def _normalize_exception(self, exc: Exception) -> ErrorEnvelope:
        """Приводит любое исключение к ErrorEnvelope."""
        # 1. Уже новый формат (если вдруг прилетает из API слоя)
        if isinstance(exc, AppError | APIClientError):
            return exc.to_envelope()
        if isinstance(exc, TelegramRetryAfter):
            return ErrorEnvelope(
                error=ErrorDetail(
                    code="telegram_retry_after",
                    message="⚠️ Слишком много запросов.",
                    details={"retry_after": exc.retry_after},
                )
            )
        telegram_map: dict[type[Exception], tuple[str, str]] = {
            TelegramForbiddenError: ("telegram_forbidden", "⚠️ Доступ запрещён."),
            TelegramUnauthorizedError: (
                "telegram_unauthorized",
                "⚠️ Ошибка авторизации.",
            ),
            TelegramNotFound: ("telegram_not_found", "⚠️ Объект не найден."),
            TelegramBadRequest: ("telegram_bad_request", "⚠️ Неверный запрос."),
            TelegramEntityTooLarge: (
                "telegram_entity_too_large",
                "⚠️ Файл слишком большой.",
            ),
            TelegramNetworkError: ("telegram_network_error", "⚠️ Ошибка сети Telegram."),
            TelegramServerError: (
                "telegram_server_error",
                "⚠️ Ошибка сервера Telegram.",
            ),
            RestartingTelegram: (
                "telegram_restarting",
                "⚠️ Telegram временно недоступен.",
            ),
            TelegramMigrateToChat: ("telegram_migrate_to_chat", "⚠️ Чат был перемещён."),
            TelegramConflictError: ("telegram_conflict", "⚠️ Конфликт токена."),
            TelegramAPIError: ("telegram_api_error", "⚠️ Ошибка Telegram API."),
        }

        for exc_type, (code, message) in telegram_map.items():
            if isinstance(exc, exc_type):
                return ErrorEnvelope(
                    error=ErrorDetail(
                        code=code,
                        message=message,
                    )
                )

        return ErrorEnvelope(
            error=ErrorDetail(
                code="unexpected_error",
                message=str(exc) or "Неизвестная ошибка",
                details={"type": type(exc).__name__},
            )
        )

    def _resolve_user_message(self, envelope: ErrorEnvelope) -> str:
        code = envelope.error.code
        message = envelope.error.message
        details = envelope.error.details

        match code:
            case "vpn_limit_reached":
                return (
                    f"⚠️ Достигнут лимит конфигов ({details.get('limit', 0)}/{details.get('limit', 0)}).\n\n"
                    f"🚀 В премиум-подписке доступно больше конфигов и расширенные возможности.\n\n"
                    f"Подключить премиум или задать вопрос:\n"
                    f"💬 @BorisisTheBlade"
                )

            case "subscription_not_found":
                return "⚠️ Подписка не найдена."

            case "telegram_retry_after":
                retry = details.get("retry_after", "?")
                return f"⚠️ Слишком много запросов. Попробуйте через {retry} секунд."

            case "telegram_bad_request":
                return f"⚠️ Неверный запрос: {message}"

            case "unexpected_error":
                return settings_bot.messages.general.common_error

            case _:
                return message

    def _log_exception(
        self, event: TelegramObject, envelope: ErrorEnvelope, exc: Exception
    ) -> None:
        user = getattr(getattr(event, "from_user", None), "id", None)
        cause = exc.__cause__
        self.logger.bind(user=user).error(
            f"\n[code] {envelope.error.code}\n"
            f"[message] {envelope.error.message}\n"
            f"[details] {envelope.error.details}\n"
            f"[cause_type] {type(cause).__name__ if cause else 'None'}\n"
            f"[cause_message] {str(cause) if cause else 'None'}"
        )

    async def _safe_send_error(self, event: TelegramObject, text: str) -> None:
        """Универсальная отправка сообщения пользователю."""
        try:
            if isinstance(event, Message):
                await event.reply(text)
            elif isinstance(event, CallbackQuery) and event.message:
                await event.message.answer(text)
        except Exception:
            self.logger.warning("Не удалось отправить ошибку пользователю")

    async def _notify_admins_envelope(
        self, event: TelegramObject, envelope: ErrorEnvelope, exc: Exception
    ) -> None:
        try:
            user = getattr(event, "from_user", None)

            if isinstance(user, User):
                user_info = f"{format_username(user)} ({user.id})"
            else:
                user_info = "Unknown user"
            cause = exc.__cause__
            msg = (
                f"⚠️ Возникла ошибка\n"
                f"user: {user_info}\n"
                f"code: {envelope.error.code}\n"
                f"message: {envelope.error.message}\n"
                f"details: {envelope.error.details}"
            )
            if cause:
                msg += (
                    f"\n[ПЕРВОПРИЧИНА]\n"
                    f"cause_type: {type(cause).__name__}\n"
                    f"cause_message: {cause}"
                )

            await send_to_admins(bot=self.bot, message_text=msg)

        except Exception:
            self.logger.warning("Ошибка при попытке уведомить админа")

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Оборачивает вызов хендлера, перехватывая и обрабатывая исключения.

        Args:
            handler: Следующий хендлер/мидлварь в цепочке aiogram.
            event: Входящее Telegram-событие.
            data: Контекстные данные aiogram, передаваемые хендлеру.

        Returns
            Any: Результат хендлера, либо None при перехваченном исключении.

        """
        try:
            return await handler(event, data)

        except Exception as exc:
            envelope = self._normalize_exception(exc)

            user_message = self._resolve_user_message(envelope)
            await self._safe_send_error(event, user_message)

            await self._notify_admins_envelope(event, envelope, exc)

            self._log_exception(event, envelope, exc)

            return None
