from typing import Any, Protocol


class HTTPClientProtocol(Protocol):
    """Контракт HTTP клиента."""

    async def get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """GET запрос."""
        ...

    async def post(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """POST запрос."""
        ...

    async def close(self) -> None:
        """Закрытие соединения."""
        ...
