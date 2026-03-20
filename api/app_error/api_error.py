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
        message = f"HTTP {status_code}"
        if detail:
            message += f": {detail}"

        super().__init__(message, cause=cause)
        self.status_code = status_code
        self.detail = detail


class APIClientConnectionError(APIClientError):
    """Ошибка соединения."""

    def __init__(
        self,
        detail: str = "Ошибка соединения с API",
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(detail, cause=cause)
