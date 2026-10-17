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

# Коды ошибок, чьё `message` заведомо написано для показа пользователю —
# все классы AppError/APIError (api/ и bot/), кроме общих/catch-all
# обработчиков непредвиденных ситуаций (unexpected_error, validation_error,
# database_error, internal_error, http_error, connection_error — их message
# либо напрямую несёт текст исключения/внешнего ответа, либо задуман как
# диагностика для лога, а не для чата). Список проверен по коду: у каждого
# класса ниже message собирается из собственных f-строк с подстановкой id/
# username/count/reason, а не из произвольного текста снаружи (см. #241).
#
# Любой НОВЫЙ код ошибки по умолчанию НЕ попадёт пользователю — его нужно
# явно добавить сюда после того, как кто-то проверил текст сообщения.
_SAFE_USER_FACING_CODES: frozenset[str] = frozenset(
    {
        # api/app_error/api_error.py
        "missing_telegram_header",
        "invalid_internal_secret",
        "admin_access_denied",
        # api/app_error/base_error.py
        "referral_not_found",
        "user_not_found",
        "role_not_found",
        "subscription_not_found",
        "subscription_error",
        "trial_alredy_used_error",
        "vpn_limit_reached",
        "transaction_not_found",
        "payment_already_processed",
        "payment_confirmation_failed",
        "payment_already_confirmed",
        "payment_canceled",
        "payment_failed",
        # bot/app_error/base_error.py
        "telegram_id_not_provided",
        "device_media_mismatch",
        "device_empty_messages",
        "device_empty_media",
        "device_instruction_mismatch",
        "vpn_node_not_found",
        "xray_not_configured",
        "proxy_not_configured",
        "news_recipients_fetch_error",
        "transaction_id_missing",
        "invalid_subscription_period",
        "subscription_activation_failed",
        "payment_link_missing",
        "no_admin_configured",
        "vpn_config_deletion_failed",
        "vpn_config_not_found",
    }
)


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
            TelegramNetworkError: (
                "telegram_network_error",
                "⚠️ Ошибка сети Telegram.",
            ),
            TelegramServerError: (
                "telegram_server_error",
                "⚠️ Ошибка сервера Telegram.",
            ),
            RestartingTelegram: (
                "telegram_restarting",
                "⚠️ Telegram временно недоступен.",
            ),
            TelegramMigrateToChat: (
                "telegram_migrate_to_chat",
                "⚠️ Чат был перемещён.",
            ),
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
                    f"⚠️ Достигнут лимит конфигов "
                    f"({details.get('current', 0)}/{details.get('limit', 0)}).\n\n"
                    f"🚀 В премиум-подписке доступно больше конфигов и расширенные возможности.\n\n"
                    f"Подключить премиум или задать вопрос:\n"
                    f"💬 @BorisisTheBlade"
                )

            case "subscription_not_found":
                return "⚠️ Подписка не найдена."

            case "vpn_node_not_found":
                return "⚠️ Эта локация сейчас недоступна, мы уже работаем над этим."

            case "telegram_retry_after":
                retry = details.get("retry_after", "?")
                return f"⚠️ Слишком много запросов. Попробуйте через {retry} секунд."

            case "unexpected_error":
                return settings_bot.messages.general.common_error

            case code if code in _SAFE_USER_FACING_CODES or code.startswith(
                "telegram_"
            ):
                # `telegram_*` коды (кроме telegram_retry_after выше) несут
                # готовый текст из telegram_map в _normalize_exception — он
                # наш собственный, не из внешнего ответа, поэтому доверяем
                # ему напрямую, а не оборачиваем в собственный шаблон (#284):
                # раньше telegram_bad_request подставлял то же сообщение в
                # f"⚠️ Неверный запрос: {message}", давая дубль в строке, а
                # остальные девять telegram_*-кодов сюда вообще не доходили.
                return message

            case _:
                # Безопасное направление по умолчанию: неизвестный/
                # непроверенный код не должен автоматически становиться
                # пользовательским текстом — он может быть техническим
                # (см. #240, #241). Подробности всё равно попадают в лог
                # через _log_exception ниже.
                return settings_bot.messages.general.common_error

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
