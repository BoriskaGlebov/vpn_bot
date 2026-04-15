import json


class APIClientError(Exception):
    """Базовая ошибка API клиента.

    Args:
        message (str): Описание ошибки.
        cause (Exception | None): Исходное исключение.

    """

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
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
        detail: str | None = None,
        *,
        cause: Exception | None = None,
    ) -> None:
        parsed_detail = self._extract_detail(detail)

        message = f"HTTP {status_code}"
        if parsed_detail:
            message += f": {parsed_detail}"

        super().__init__(message, cause=cause)

        self.status_code = status_code
        self.detail = parsed_detail

    @staticmethod
    def _extract_detail(detail: str | None) -> str:
        """Безопасно извлекает detail из ответа."""
        if not detail:
            return "Деталей нет."

        try:
            data = json.loads(detail)

            # FastAPI формат: {"detail": "..."}
            if isinstance(data, dict):
                return data.get("detail", str(data))

            return str(data)

        except (json.JSONDecodeError, TypeError):
            # если это просто строка
            return detail


class APIClientConnectionError(APIClientError):
    """Ошибка соединения."""

    def __init__(
        self,
        detail: str = "Ошибка соединения с API",
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(detail, cause=cause)


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


def map_http_error(
    status_code: int,
    detail: str | None,
) -> APIClientHTTPError:
    """Маппит HTTP статус в конкретный тип ошибки API клиента.

    Преобразует числовой HTTP статус-код в специализированное
    исключение, что позволяет обрабатывать ошибки по типу,
    а не по числовому коду.

    Args:
        status_code (int): HTTP статус-код ответа.
        detail (str | None): Тело ответа или описание ошибки.

    Returns
        APIClientHTTPError: Экземпляр соответствующего класса ошибки.

    """
    match status_code:
        case 401:
            return APIClientUnauthorizedError(status_code, detail)
        case 403:
            return APIClientForbiddenError(status_code, detail)
        case 404:
            return APIClientNotFoundError(status_code, detail)
        case 409:
            return APIClientConflictError(status_code, detail)
        case 422:
            return APIClientValidationError(status_code, detail)
        case _:
            return APIClientHTTPError(status_code, detail)
