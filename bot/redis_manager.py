import json
from typing import Any, cast

from redis.asyncio import Redis

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

    DEFAULT_EXPIRE = 3600

    def __init__(self, redis_url: str) -> None:
        self.url = redis_url
        self.client: Redis | None = None

    async def connect(self) -> Redis:
        """Инициализирует соединение с Redis.

        Returns
            Redis: Клиент Redis.

        Raises
            Exception: Если соединение не удалось установить.

        """
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
        """Возвращает значение по ключу.

        Args:
            key (str): Ключ для получения значения.

        Returns
            str | None: Значение ключа или None, если ключ не найден.

        """
        redis = await self._ensure_connection()
        value = await redis.get(key)
        return cast(str | None, value)

    async def set(self, key: str, value: str, expire: int | None = None) -> None:
        """Сохраняет значение по ключу с опциональным временем жизни.

        Args:
            key (str): Ключ для сохранения значения.
            value (str): Значение для сохранения.
            expire (int | None): Время жизни ключа в секундах. Если None, используется DEFAULT_EXPIRE.

        """
        redis = await self._ensure_connection()
        ttl = expire or self.DEFAULT_EXPIRE
        await redis.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        """Удаляет ключ из Redis.

        Args:
            key (str): Ключ для удаления.

        """
        redis = await self._ensure_connection()
        await redis.delete(key)

    async def save_admin_message(
        self, user_id: int, admin_id: int, message_id: int, expire: int | None = None
    ) -> None:
        """Сохраняет идентификаторы сообщений администраторов для пользователя.

        Args:
            user_id (int): Telegram ID пользователя.
            admin_id (int): Telegram ID администратора.
            message_id (int): ID сообщения в чате.
            expire (int | None): Время жизни ключа в секундах. По умолчанию DEFAULT_EXPIRE.

        """
        redis = await self._ensure_connection()
        key = f"admin_messages:{user_id}"
        existing = await redis.get(key)
        messages: list[dict[str, Any]] = json.loads(existing) if existing else []
        messages.append({"chat_id": admin_id, "message_id": message_id})
        ttl = expire or self.DEFAULT_EXPIRE
        await redis.set(key, json.dumps(messages), ex=ttl)
        logger.debug(f"💾 Сохранены админские сообщения user_id={user_id} с TTL={ttl}")

    async def get_admin_messages(self, user_id: int) -> list[dict[str, Any]]:
        """Возвращает список сообщений администраторов для пользователя.

        Args:
            user_id (int): Telegram ID пользователя.

        Returns
            list[dict[str, Any]]: Список сообщений, каждое в формате {"chat_id": int, "message_id": int}.

        """
        redis = await self._ensure_connection()
        key = f"admin_messages:{user_id}"
        data = await redis.get(key)
        return json.loads(data) if data else []

    async def clear_admin_messages(self, user_id: int) -> None:
        """Удаляет все сообщения администраторов, связанные с пользователем.

        Args:
            user_id (int): Telegram ID пользователя.

        """
        redis = await self._ensure_connection()
        key = f"admin_messages:{user_id}"
        await redis.delete(key)
        logger.debug(f"🗑️ Очищены сообщения админов для user_id={user_id}")


redis_manager = SettingsRedis(str(settings_db.REDIS_URL))
