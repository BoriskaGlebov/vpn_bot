from abc import ABC, abstractmethod
from typing import Any

from redis.asyncio import Redis


class RedisClientProtocol(ABC):
    """Абстракция клиента хранилища (Redis-like)."""

    @abstractmethod
    async def get(self, key: str) -> Any:
        """Метод получения значения по ключу."""
        ...

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        """Метод установки значения."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Удалить значения."""
        ...

    @abstractmethod
    async def connect(self) -> Redis:
        """Подключения в Redis."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Отключения от базы."""
        ...
