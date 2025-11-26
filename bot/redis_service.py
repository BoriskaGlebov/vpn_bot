from typing import Any

import orjson
from loguru._logger import Logger

from bot.config import logger
from bot.redis_manager import SettingsRedis, redis_manager


class RedisAdminMessageStorage:
    """Хранение сообщений администраторов в Redis."""

    def __init__(self, redis: SettingsRedis, logger: Logger) -> None:
        self.redis = redis
        self.logger = logger

    def _key(self, user_id: int) -> str:
        return f"admin_messages:{user_id}"

    async def add(self, user_id: int, admin_id: int, message_id: int) -> None:
        """Сохраняет идентификаторы сообщений администраторов для пользователя.

        Args:
            user_id (int): Telegram ID пользователя.
            admin_id (int): Telegram ID администратора.
            message_id (int): ID сообщения в чате.

        """
        key = self._key(user_id)
        existing = await self.redis.get(key)

        messages: list[dict[str, Any]] = []
        if existing:
            try:
                messages = orjson.loads(existing)
            except orjson.JSONDecodeError:
                messages = []

        messages.append({"chat_id": admin_id, "message_id": message_id})
        await self.redis.set(key, orjson.dumps(messages))
        self.logger.debug(f"💾 Сохранены админские сообщения user_id={user_id}")

    async def get(self, user_id: int) -> list[dict[str, Any]]:
        """Возвращает список сообщений администраторов для пользователя.

        Args:
            user_id (int): Telegram ID пользователя.

        Returns
            list[dict[str, Any]]: Список сообщений, каждое в формате {"chat_id": int, "message_id": int}.

        """
        key = self._key(user_id)
        data = await self.redis.get(key)
        return orjson.loads(data) if data else []

    async def clear(self, user_id: int) -> None:
        """Удаляет все сообщения администраторов, связанные с пользователем.

        Args:
            user_id (int): Telegram ID пользователя.

        """
        key = self._key(user_id)
        await self.redis.delete(key)
        self.logger.debug(f"🗑️ Очищены сообщения админов для user_id={user_id}")


redis_admin_mess_storage = RedisAdminMessageStorage(redis_manager, logger)
