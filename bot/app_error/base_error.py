from typing import Any

from bot.app_error.schema import ErrorDetail, ErrorEnvelope


class AppError(Exception):
    """Базовое доменное исключение."""

    code: str = "app_error"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"[{self.code}] {message}")

        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )


class MessageNotFoundError(AppError):
    """Ошибка сообщения для редактирования не найдено."""

    code: str = "message_not_found"
    status_code: int = 404

    def __init__(self) -> None:
        super().__init__(message="Сообщение для редактирования не найдено")


class UserNotFoundError(AppError):
    code = "user_not_found"
    status_code = 404

    def __init__(self, tg_id: int) -> None:
        super().__init__(
            message=f"Пользователь с Telegram ID {tg_id} не найден",
            details={"tg_id": tg_id},
        )
        self.tg_id = tg_id


class SubscriptionNotFoundError(AppError):
    code = "subscription_not_found"
    status_code = 404

    def __init__(self, tg_id: int) -> None:
        super().__init__(
            message=f"У пользователя {tg_id} нет активной подписки",
            details={"tg_id": tg_id},
        )
        self.tg_id = tg_id


class VPNLimitError(AppError):
    code = "vpn_limit_reached"
    status_code = 429

    def __init__(self, tg_id: int, limit: int, username: str = "") -> None:
        super().__init__(
            message=f"Пользователь достиг лимита VPN-конфигов ({limit})",
            details={
                "tg_id": tg_id,
                "limit": limit,
                "username": username,
            },
        )

        self.tg_id = tg_id
        self.limit = limit
        self.username = username


class TelegramIdNotProvidedError(AppError):
    code = "telegram_id_not_provided"
    status_code = 400

    def __init__(self, message: str | None=None) -> None:
        super().__init__(
            message=message or "В callback отсутствует telegram_id",
        )

class DeviceMediaMismatchError(AppError):
    code = "device_media_mismatch"
    status_code = 500

    def __init__(self, device: str, media_len: int, messages_len: int) -> None:
        super().__init__(
            message=f"{device}: media ({media_len}) != messages ({messages_len})",
            details={
                "media_len": media_len,
                "messages_len": messages_len,
            },
        )

class DeviceEmptyMessagesError(AppError):
    code = "device_empty_messages"
    status_code = 500

    def __init__(self, device: str) -> None:
        super().__init__(
            message=f"{device}: пустой список инструкций",
            details={"device": device},
        )

class DeviceEmptyMediaError(AppError):
    code = "device_empty_media"
    status_code = 500

    def __init__(self, device: str) -> None:
        super().__init__(
            message=f"{device}: нет файлов в S3",
            details={"device": device},
        )

class DeviceInstructionMismatchError(AppError):
    code = "device_instruction_mismatch"
    status_code = 500

    def __init__(self, device: str, media: int, messages: int) -> None:
        super().__init__(
            message=(
                f"{device}: несоответствие длин media({media}) и messages({messages})."
                "Ожидается: вступление + подписи ко всем фото (+ опционально финал)"
            ),
            details={
                "media": media,
                "messages": messages,
            },
        )