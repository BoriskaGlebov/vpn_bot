import json
from typing import Any, cast

from redis.asyncio import Redis

from bot.config import logger, settings_db


class SettingsRedis:
    """Настройки и инициализация отдельного клиента Redis для хранения данных вне FSM."""

    def __init__(self, redis_url: str) -> None:
        self.url = redis_url
        self.client: Redis | None = None

    async def connect(self) -> Redis:
        """Инициализирует соединение с Redis."""
        if self.client is None:
            self.client = Redis.from_url(self.url, decode_responses=True)
            try:
                await self.client.ping()
                logger.info("✅ Подключение к Redis установлено успешно")
            except Exception as e:
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

    async def get(self, key: str) -> str | None:
        """Возвращает значение по ключу."""
        redis = await self._ensure_connection()
        value = await redis.get(key)
        return cast(str | None, value)

    async def set(self, key: str, value: str, expire: int | None = None) -> None:
        """Сохраняет значение по ключу."""
        redis = await self._ensure_connection()
        await redis.set(key, value, ex=expire)

    async def delete(self, key: str) -> None:
        """Удаляет ключ из Redis."""
        redis = await self._ensure_connection()
        await redis.delete(key)

    async def save_admin_message(
        self, user_id: int, admin_id: int, message_id: int
    ) -> None:
        """Сохраняет идентификаторы сообщений администраторов для конкретного пользователя."""
        redis = await self._ensure_connection()
        key = f"admin_messages:{user_id}"
        existing = await redis.get(key)
        messages: list[dict[str, Any]] = json.loads(existing) if existing else []
        messages.append({"chat_id": admin_id, "message_id": message_id})
        await redis.set(key, json.dumps(messages))

    async def get_admin_messages(self, user_id: int) -> list[dict[str, Any]]:
        """Возвращает список сообщений администраторов для пользователя."""
        redis = await self._ensure_connection()
        key = f"admin_messages:{user_id}"
        data = await redis.get(key)
        return json.loads(data) if data else []

    async def clear_admin_messages(self, user_id: int) -> None:
        """Удаляет все сообщения администраторов, связанные с пользователем."""
        redis = await self._ensure_connection()
        key = f"admin_messages:{user_id}"
        await redis.delete(key)
        logger.debug(f"🗑️ Очищены сообщения админов для user_id={user_id}")


redis_manager = SettingsRedis(str(settings_db.REDIS_URL))
