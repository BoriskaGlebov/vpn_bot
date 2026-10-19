from typing import Any

from starlette import status

from api.core.exceptions.schema import ErrorDetail, ErrorEnvelope


class APIError(Exception):
    """Базовая ошибка API."""

    code: str = "api_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Сериализует ошибку в словарь."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }

    def to_envelope(
        self,
    ) -> ErrorEnvelope:
        """Сериализует ошибку в ErrorEnvelope."""
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details or {},
            )
        )


class APIClientHTTPError(APIError):
    """HTTP-ошибка клиента API."""

    code = "http_error"

    def __init__(
        self,
        message: str = "Ошибка API",
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        details = details or {}
        super().__init__(
            message=f"HTTP {status_code}: {message}",
            details={"status_code": status_code, **details},
            cause=cause,
        )


class APIClientConnectionError(APIError):
    """Ошибка соединения с внешним API."""

    code = "connection_error"

    def __init__(
        self,
        message: str = "Ошибка соединения с API",
        *,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message=message, details=details, cause=cause)


class MissingTelegramHeaderError(APIError):
    """Отсутствует обязательный заголовок Telegram."""

    code = "missing_telegram_header"
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, header_name: str = "X-Telegram-Id") -> None:
        self.header_name = header_name
        super().__init__(
            message=f"Обязательный заголовок {header_name} отсутствует",
            details={
                "header": header_name,
            },
        )


class InvalidInternalSecretError(APIError):
    """Ошибка неверного/отсутствующего внутреннего секрета bot/ <-> api/.

    Возникает, если заголовок ``X-Internal-Secret`` отсутствует или не
    совпадает с ``settings_api.internal_api_secret``. В обычной работе это
    выставляет только ``AuthMiddleware`` (запрос даже не доходит до роута
    с валидным пользователем), но эта ошибка нужна, чтобы то же самое было
    видно и проверяемо через Swagger — там заголовок можно ввести вручную
    через кнопку Authorize.
    """

    code = "invalid_internal_secret"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__(
            message="Заголовок X-Internal-Secret отсутствует или неверен",
        )


class AdminNotFoundHeaderError(APIError):
    """Пользователь не является администратором."""

    code = "admin_access_denied"
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, tg_id: int) -> None:
        super().__init__(
            message=f"Отказано в доступе для tg_id={tg_id}. Пользователь не админ.",
            details={
                "tg_id": tg_id,
            },
        )
