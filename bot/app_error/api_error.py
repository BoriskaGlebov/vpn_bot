import json
from typing import Any

from pydantic import ValidationError

from bot.app_error.schema import ErrorDetail, ErrorEnvelope


class APIClientError(Exception):
    """Базовая ошибка API клиента.

    Args:
        message (str): Описание ошибки.
        cause (Exception | None): Исходное исключение.

    """

    def __init__(self, error: ErrorDetail, *, cause: Exception | None = None) -> None:
        self.error = error
        super().__init__(f"[{error.code}] {error.message}")
        self.cause = cause

    def __str__(self) -> str:
        """Строковое представление."""
        base = super().__str__()
        if self.cause:
            return f"{base} (cause: {self.cause})"
        return base


class APIClientHTTPError(APIClientError):
    """Ошибка HTTP уровня (4xx, 5xx)."""

    def __init__(
        self,
        status_code: int,
        error: ErrorDetail,
        *,
        cause: Exception | None = None,
    ) -> None:
        self.status_code = status_code

        super().__init__(error,cause=cause)


class APIClientConnectionError(APIClientError):
    """Ошибка соединения."""

    def __init__(
        self,
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(error= ErrorDetail(
                code="connection_error",
                message="⚠️ Не удалось подключиться к API",
            ), cause=cause)


class APIClientUnauthorizedError(APIClientHTTPError):
    """Ошибка 401 Unauthorized."""

    pass


class APIClientForbiddenError(APIClientHTTPError):
    """Ошибка 403 Forbidden."""

    pass


class APIClientNotFoundError(APIClientHTTPError):
    """Ошибка 404 Not Found."""

    pass


class APIClientValidationError(APIClientHTTPError):
    """Ошибка 422 Validation Error."""

    pass


class APIClientConflictError(APIClientHTTPError):
    """Ошибка 409 Conflict."""

    pass

def parse_api_error(body: dict[str, Any]  )-> ErrorDetail:


    try:
        envelope = ErrorEnvelope.model_validate(body)
        return envelope.error
    except ValidationError:
        raise

def map_http_error(
    status_code: int,
    response_body: dict[str, Any],
) -> APIClientHTTPError:
    """Маппит HTTP статус в конкретный тип ошибки API клиента.

    Преобразует числовой HTTP статус-код в специализированное
    исключение, что позволяет обрабатывать ошибки по типу,
    а не по числовому коду.

    Args:
        status_code (int): HTTP статус-код ответа.
        response_body (dict[str, Any] | None): Тело ответа или описание ошибки.

    Returns
        APIClientHTTPError: Экземпляр соответствующего класса ошибки.

    """
    error = parse_api_error(response_body)

    match status_code:
        case 401:
            return APIClientUnauthorizedError(status_code, error)
        case 403:
            return APIClientForbiddenError(status_code, error)
        case 404:
            return APIClientNotFoundError(status_code, error)
        case 409:
            return APIClientConflictError(status_code, error)
        case 422:
            return APIClientValidationError(status_code, error)
        case _:
            return APIClientHTTPError(status_code, error)
