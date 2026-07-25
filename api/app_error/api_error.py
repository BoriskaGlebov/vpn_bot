from typing import Any

from starlette import status

from api.core.exceptions.schema import ErrorDetail, ErrorEnvelope


class APIError(Exception):
    """Базовое исключение API.

    Используется как корневой класс для всех ошибок клиентского API.
    Позволяет унифицировать формат ошибок и преобразование в DTO.

    Attributes
        code: Машиночитаемый код ошибки.
        status_code: HTTP статус код ответа.
        message: Человекочитаемое сообщение об ошибке.
        details: Дополнительные структурированные данные об ошибке.
        cause: Исходное исключение, вызвавшее данную ошибку.

    """

    code: str = "api_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Инициализирует базовую ошибку API.

        Args:
            message: Текст ошибки для пользователя или логирования.
            details: Дополнительные данные об ошибке (опционально).
            cause: Первопричина ошибки (исходное исключение), если есть.

        """
        super().__init__(message)

        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Преобразует исключение в словарь.

        Returns
            Словарь, соответствующий стандартному формату API ошибки.

        """
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
        """Преобразует исключение в Pydantic-обёртку ответа API.

        Returns
            ErrorEnvelope с заполненными данными ошибки.

        """
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details or {},
            )
        )


class APIClientHTTPError(APIError):
    """Ошибка HTTP-уровня клиента (4xx / 5xx ответы внешнего API).

    Используется, когда внешний сервис вернул ошибочный HTTP-ответ.
    """

    code = "http_error"

    def __init__(
        self,
        message: str = "Ошибка API",
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Инициализирует HTTP ошибку клиента.

        Args:
            message: Базовое сообщение об ошибке.
            status_code: HTTP статус код ответа внешнего сервиса.
            details: Дополнительные данные (например, тело ответа).
            cause: Исходное исключение, если есть.

        """
        self.status_code = status_code
        details = details or {}
        super().__init__(
            message=f"HTTP {status_code}: {message}",
            details={"status_code": status_code, **details},
            cause=cause,
        )


class APIClientConnectionError(APIError):
    """Ошибка соединения с внешним API.

    Возникает при сетевых сбоях, таймаутах или недоступности сервиса.
    """

    code = "connection_error"

    def __init__(
        self,
        message: str = "Ошибка соединения с API",
        *,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Инициализирует HTTP ошибку клиента.

        Args:
            message: Базовое сообщение об ошибке.
            status_code: HTTP статус код ответа внешнего сервиса.
            details: Дополнительные данные (например, тело ответа).
            cause: Исходное исключение, если есть.

        """
        self.status_code = status_code
        super().__init__(message=message, details=details, cause=cause)


class MissingTelegramHeaderError(APIError):
    """Ошибка отсутствия обязательного HTTP-заголовка Telegram.

    Возникает, если в запросе отсутствует заголовок авторизации Telegram.
    """

    code = "missing_telegram_header"
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, header_name: str = "X-Telegram-Id") -> None:
        """Инициализирует ошибку отсутствующего заголовка.

        Args:
            header_name: Название обязательного HTTP-заголовка.

        """
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
        """Инициализирует ошибку неверного внутреннего секрета."""
        super().__init__(
            message="Заголовок X-Internal-Secret отсутствует или неверен",
        )


class AdminNotFoundHeaderError(APIError):
    """Ошибка отсутствия административных прав у пользователя.

    Возникает, когда пользователь с указанным tg_id не является администратором.
    """

    code = "admin_access_denied"
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, tg_id: int) -> None:
        """Инициализирует ошибку отсутствия прав администратора.

        Args:
            tg_id: Telegram ID пользователя, которому отказано в доступе.

        """
        super().__init__(
            message=f"Отказано в доступе для tg_id={tg_id}. Пользователь не админ.",
            details={
                "tg_id": tg_id,
            },
        )
