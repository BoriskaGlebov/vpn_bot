class APIClientError(Exception):
    """Базовая ошибка API клиента."""


class APIClientHTTPError(APIClientError):
    """Ошибка HTTP уровня (4xx, 5xx)."""

    def __init__(self, status_code: int, detail: str | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class APIClientConnectionError(APIClientError):
    """Ошибка соединения."""
