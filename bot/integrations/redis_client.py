from typing import Any

import orjson
from loguru import logger
from redis import RedisError
from redis.asyncio import Redis

from shared.interfaces.redis_client import RedisClientProtocol


class RedisClient(RedisClientProtocol):
    """Класс для управления соединением и хранением данных в Redis вне FSM.

    Позволяет сохранять, получать и удалять данные, а также хранить сообщения администраторов
    и сообщения о заказах с опциональным временем жизни.

    Attributes
        DEFAULT_EXPIRE (int): Время жизни ключей в Redis по умолчанию (в секундах, 86400 = 24 часа).
        url (str): URL подключения к Redis.
        client (Redis | None): Клиент Redis.
        default_expire (int | None): Время жизни ключей в Redis по умолчанию (в секундах, 86400 = 24 часа).

    """

    DEFAULT_EXPIRE = 8400

    def __init__(self, redis_url: str, default_expire: int | None = None) -> None:
        self.url = redis_url
        self.client: Redis | None = None
        self.default_expire = default_expire or self.DEFAULT_EXPIRE

    async def connect(self) -> Redis:
        """Инициализирует соединение с Redis.

        Returns
            Redis: Клиент Redis.

        Raises
            Exception: Если соединение не удалось установить.

        """
        if self.client is None:
            self.client = Redis.from_url(self.url, decode_responses=False)
            try:
                await self.client.ping()
                logger.info("✅ Подключение к Redis установлено успешно")
            except RedisError as e:
                logger.error(f"❌ Ошибка подключения к Redis: {e}")
        return self.client

    async def disconnect(self) -> None:
        """Закрывает соединение с Redis."""
        if self.client:
            await self.client.close()
            logger.info("🔒 Соединение с Redis закрыто")
            self.client = None

    async def _ensure_connection(self) -> Redis:
        """Гарантирует активное соединение с Redis."""
        if self.client is None:
            logger.warning("Redis-клиент не инициализирован, переподключение...")
            await self.connect()
        assert self.client is not None
        return self.client

    async def get(self, key: str) -> Any:
        """Возвращает значение по ключу.

        Args:
            key (str): Ключ для получения значения.

        Returns
            Any: Значение ключа или None, если ключ не найден.

        """
        redis = await self._ensure_connection()
        row = await redis.get(key)

        return orjson.loads(row) if row else None

    async def set(
        self, key: str, value: Any, expire: int | None = None, nx: bool = False
    ) -> bool | None:
        """Сохраняет значение по ключу с опциональным временем жизни.

        Args:
            nx (bool): Not exist проверка на существование.
            key (str): Ключ для сохранения значения.
            value (Any): Значение для сохранения.
            expire (int | None): Время жизни ключа в секундах. Если None, используется DEFAULT_EXPIRE.

        """
        redis = await self._ensure_connection()
        ttl = expire or self.default_expire
        row = orjson.dumps(value)
        res = await redis.set(key, row, ex=ttl, nx=nx)
        return res

    async def delete(self, key: str) -> None:
        """Удаляет ключ из Redis.

        Args:
            key (str): Ключ для удаления.

        """
        redis = await self._ensure_connection()
        await redis.delete(key)
