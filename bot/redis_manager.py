from typing import Any

import orjson
from loguru._logger import Logger
from redis.asyncio import Redis
from redis.exceptions import RedisError

from bot.config import logger, settings_db


class SettingsRedis:
    """Класс для управления соединением и хранением данных в Redis вне FSM.

    Позволяет сохранять, получать и удалять данные, а также хранить сообщения администраторов
    и сообщения о заказах с опциональным временем жизни.

    Attributes
        DEFAULT_EXPIRE (int): Время жизни ключей в Redis по умолчанию (в секундах, 86400 = 24 часа).
        url (str): URL подключения к Redis.
        client (Redis | None): Клиент Redis.

    """

    DEFAULT_EXPIRE = settings_db.default_expire

    def __init__(self, redis_url: str, logger: Logger) -> None:
        self.url = redis_url
        self.client: Redis | None = None
        self.logger = logger

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
                self.logger.info("✅ Подключение к Redis установлено успешно")
            except RedisError as e:
                self.logger.error(f"❌ Ошибка подключения к Redis: {e}")
        return self.client

    async def disconnect(self) -> None:
        """Закрывает соединение с Redis."""
        if self.client:
            await self.client.close()
            self.logger.info("🔒 Соединение с Redis закрыто")
            self.client = None

    async def _ensure_connection(self) -> Redis:
        """Гарантирует активное соединение с Redis."""
        if self.client is None:
            self.logger.warning("Redis-клиент не инициализирован, переподключение...")
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
    ) -> str | None:
        """Сохраняет значение по ключу с опциональным временем жизни.

        Args:
            nx (bool| None): Not exist проверка на существование.
            key (str): Ключ для сохранения значения.
            value (Any): Значение для сохранения.
            expire (int | None): Время жизни ключа в секундах. Если None, используется DEFAULT_EXPIRE.

        """
        redis = await self._ensure_connection()
        ttl = expire or self.DEFAULT_EXPIRE
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


redis_manager = SettingsRedis(str(settings_db.redis_url), logger=logger)  # type: ignore[arg-type]
