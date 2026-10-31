import hashlib
from typing import Any
from uuid import UUID

from loguru import logger

from bot.integrations.redis_client import RedisClient


class RedisPaymentMessageStorage:
    """Хранит в Redis сообщение бота со ссылкой на оплату картой.

    Нужно, чтобы по приходу вебхука платёжного шлюза отредактировать именно
    то сообщение с кнопкой "Перейти к оплате" (убрать устаревшую ссылку и
    показать итог), а не оставлять пользователю неактуальный экран.
    """

    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    def _key(self, transaction_id: UUID | str) -> str:
        return f"payment_message:{transaction_id}"

    async def save(
        self,
        transaction_id: UUID | str,
        chat_id: int,
        message_id: int,
        expire: int = 86400,
    ) -> None:
        """Сохраняет расположение сообщения с оплатой для транзакции.

        Args:
            transaction_id (UUID | str): Идентификатор платёжной транзакции.
            chat_id (int): ID чата, в котором показано сообщение.
            message_id (int): ID сообщения с кнопкой "Перейти к оплате".
            expire (int): Время жизни записи в секундах (по умолчанию сутки —
                дольше платёжная ссылка не актуальна в любом случае).

        """
        key = self._key(transaction_id)
        await self.redis.set(
            key, {"chat_id": chat_id, "message_id": message_id}, expire=expire
        )
        logger.debug(f"💾 Сохранено сообщение оплаты transaction_id={transaction_id}")

    async def pop(self, transaction_id: UUID | str) -> dict[str, int] | None:
        """Возвращает и удаляет сохранённое сообщение оплаты (одноразово).

        Args:
            transaction_id (UUID | str): Идентификатор платёжной транзакции.

        Returns
            dict[str, int] | None: {"chat_id": int, "message_id": int}, либо
            None, если сообщение не найдено (истёк TTL или его не было —
            например, оплата переводом, а не картой).

        """
        key = self._key(transaction_id)
        data = await self.redis.get(key)
        if data is not None:
            await self.redis.delete(key)
        return data


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


class RedisNewsBroadcastStorage:
    """Хранит прогресс рассылки сообщения списку получателей.

    Нужно, чтобы деплой или падение процесса в середине рассылки не терял
    оставшихся получателей и не дублировал доставку тем, кто сообщение уже
    получил: раньше прогресс жил только в памяти цикла и пропадал
    вместе с процессом.

    Используется и рассылкой новостей (`/news`), и рассылкой по выбранным
    пользователям из админки — у каждой свой `key`, иначе параллельные
    рассылки затирали бы прогресс друг друга в одной записи Redis.

    Args:
        redis: Клиент Redis.
        key: Ключ хранения прогресса. По умолчанию — ключ рассылки новостей.

    """

    _KEY = "news_broadcast:pending"

    def __init__(self, redis: RedisClient, key: str | None = None) -> None:
        self.redis = redis
        self._key = key or self._KEY

    async def save(self, news: dict[str, Any], recipients: list[int]) -> None:
        """Сохраняет новость и список получателей, которым она ещё не отправлена.

        Args:
            news (dict[str, Any]): Данные новости (тип контента, текст/медиа).
            recipients (list[int]): Telegram ID получателей, которым рассылка
                ещё не доставлена.

        """
        await self.redis.set(self._key, {"news": news, "recipients": recipients})

    async def get(self) -> dict[str, Any] | None:
        """Возвращает сохранённую рассылку, если она не была завершена.

        Returns
            dict[str, Any] | None: {"news": ..., "recipients": [...]},
            либо None, если незавершённой рассылки нет.

        """
        data = await self.redis.get(self._key)
        return data or None

    async def update_recipients(self, recipients: list[int]) -> None:
        """Обновляет список получателей, которым рассылка ещё не доставлена.

        Args:
            recipients (list[int]): Оставшиеся Telegram ID.

        """
        data = await self.get()
        if data is None:
            return
        data["recipients"] = recipients
        await self.redis.set(self._key, data)

    async def clear(self) -> None:
        """Удаляет сохранённый прогресс — рассылка завершена."""
        await self.redis.delete(self._key)


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
