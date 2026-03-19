import hashlib
from typing import Any

from loguru import logger

from bot.integrations.redis_client import RedisClient, redis_manager


class RedisAdminMessageStorage:
    """Хранение сообщений администраторов в Redis."""

    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    def _key(self, user_id: int) -> str:
        return f"admin_messages:{user_id}"

    async def add(self, user_id: int, admin_id: int | str, message_id: int) -> None:
        """Сохраняет идентификаторы сообщений администраторов для пользователя.

        Args:
            user_id (int): Telegram ID пользователя.
            admin_id (int|str): Telegram ID администратора.
            message_id (int): ID сообщения в чате.

        """
        key = self._key(user_id)
        existing = await self.redis.get(key)

        messages: list[dict[str, Any]] = existing or []

        messages.append({"chat_id": admin_id, "message_id": message_id})
        await self.redis.set(key, messages)
        logger.debug(f"💾 Сохранены админские сообщения user_id={user_id}")

    async def get(self, user_id: int) -> list[dict[str, Any]]:
        """Возвращает список сообщений администраторов для пользователя.

        Args:
            user_id (int): Telegram ID пользователя.

        Returns
            list[dict[str, Any]]: Список сообщений, каждое в формате {"chat_id": int, "message_id": int}.

        """
        key = self._key(user_id)
        data = await self.redis.get(key)
        return data or []

    async def clear(self, user_id: int) -> None:
        """Удаляет все сообщения администраторов, связанные с пользователем.

        Args:
            user_id (int): Telegram ID пользователя.

        """
        key = self._key(user_id)
        await self.redis.delete(key)
        logger.debug(f"🗑️ Очищены сообщения админов для user_id={user_id}")


class RedisEmbeddingCache:
    """Redis-кэш для хранения эмбеддингов текстов.

    Используется для ускорения генерации эмбеддингов через внешние API
    (например, Yandex AI Studio) и уменьшения количества повторных запросов.

    Attributes
        _redis (SettingsRedis): Асинхронный клиент Redis.

    """

    def __init__(self, redis: RedisClient) -> None:
        """Инициализация Redis-кэша.

        Args:
            redis (RedisClient): Асинхронный Redis клиент.

        """
        self._redis = redis

    def _key(self, text: str) -> str:
        """Генерация уникального ключа для текста в Redis.

        Используется SHA256 хеширование, чтобы ключ был безопасным и фиксированной длины.

        Args:
            text (str): Текст, для которого нужно создать ключ.

        Returns
            str: Уникальный ключ для хранения в Redis.

        """
        digest = hashlib.sha256(text.encode()).hexdigest()
        return f"embedding:{digest}"

    async def get(self, text: str) -> list[float] | None:
        """Получить эмбеддинг текста из Redis-кэша.

        Args:
            text (str): Текст запроса.

        Returns
            Optional[List[float]]: Эмбеддинг, если он найден в кэше, иначе None.

        """
        key = self._key(text)

        value = await self._redis.get(key)

        if value is not None:
            logger.debug("Embedding кэш получен для ключа {}", key)
        else:
            logger.debug("Embedding отсутствует в кэше для ключа {}", key)

        return value

    async def set(self, text: str, embedding: list[float]) -> None:
        """Сохранить эмбеддинг текста в Redis-кэш.

        Args:
            text (str): Текст запроса.
            embedding (List[float]): Список значений эмбеддинга.

        """
        key = self._key(text)

        await self._redis.set(key=key, value=embedding, expire=86400)

        logger.debug("Embedding кэш сохранен для ключа {}", key)


redis_admin_mess_storage = RedisAdminMessageStorage(redis_manager)
redis_embedding_cache = RedisEmbeddingCache(redis_manager)
