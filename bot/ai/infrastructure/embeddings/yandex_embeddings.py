import asyncio
import logging
from typing import Any

import numpy as np
from langchain_core.embeddings import Embeddings
from loguru import logger
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential
from yandex_ai_studio_sdk import AsyncAIStudio

from bot.redis_service import RedisEmbeddingCache


class YandexEmbeddings(Embeddings):
    """Сервис генерации эмбеддингов через Yandex AI Studio.

    Использует удалённую модель `text-search-query`.

    Attributes
        _sdk (AsyncAIStudio): Клиент Yandex AI Studio.
        _model: Экземпляр модели эмбеддингов.
        _normalize (bool): Флаг L2-нормализации векторов.

    """

    def __init__(
        self,
        folder_id: str,
        api_key: str,
        cache: RedisEmbeddingCache | None = None,
        normalize: bool = True,
    ) -> None:
        """Инициализирует Yandex embeddings сервис.

        Args:
            folder_id: ID папки Yandex Cloud.
            api_key: API ключ доступа.
            cache: Кэширование результатов эмбеддинга.
            normalize: Выполнять ли L2-нормализацию.

        """
        self._normalize = normalize
        self._sdk = AsyncAIStudio(folder_id=folder_id, auth=api_key)
        self._model = self._sdk.models.text_embeddings("text-search-query")
        self._cache = cache
        logger.info(
            "YandexEmbeddings инициализировано | model=text-search-query normalize={}",
            normalize,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _run_embedding(self, text: str) -> Any:
        """Безопасный вызов Yandex API с retry."""
        logger.debug("Embedding request | text_length={}", len(text))

        result = await self._model.run(text)

        return result

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Генерация эмбеддингов для списка текстов.

        Сначала проверяет Redis-кэш. Если эмбеддинг отсутствует,
        выполняется запрос к Yandex API.

        Args:
            texts: Список текстов.

        Returns
            Список эмбеддингов.

        """
        cached_vectors: dict[int, list[float]] = {}
        missing_texts: list[str] = []
        missing_indexes: list[int] = []

        if self._cache:
            cache_tasks = [self._cache.get(text) for text in texts]
            cached_results = await asyncio.gather(*cache_tasks)

            for i, cached in enumerate(cached_results):
                if cached:
                    cached_vectors[i] = cached
                else:
                    missing_texts.append(texts[i])
                    missing_indexes.append(i)
        else:
            missing_texts = texts
            missing_indexes = list(range(len(texts)))

        new_vectors: list[list[float]] = []

        if missing_texts:
            coros = [self._run_embedding(text) for text in missing_texts]

            results = await asyncio.gather(*coros)

            vectors = np.array([r.embedding for r in results])

            if self._normalize:
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                vectors = vectors / norms

            new_vectors = vectors.tolist()

            logger.info(
                "Сгенерировано {} новых эмбеддингов через Yandex API",
                len(new_vectors),
            )

            if self._cache:
                cache_tasks = [
                    self._cache.set(text, vec)
                    for text, vec in zip(missing_texts, new_vectors)
                ]
                await asyncio.gather(*cache_tasks)

        final_vectors: list[list[float]] = [None] * len(texts)  # type: ignore

        for idx, vec in cached_vectors.items():
            final_vectors[idx] = vec

        for idx, vec in zip(missing_indexes, new_vectors):
            final_vectors[idx] = vec

        return final_vectors

    async def aembed_query(self, text: str) -> list[float]:
        """Генерация эмбеддинга для одного запроса через Yandex API.

        Args:
            text (str): Текст запроса.

        Returns
            List[float]: Эмбеддинг запроса.

        """
        if self._cache:
            cached = await self._cache.get(text)
            if cached:
                return cached
        result = await self._run_embedding(text)
        logger.debug(f"tokens: {result.num_tokens}")
        vector = np.array(result.embedding)

        if self._normalize:
            vector = vector / np.linalg.norm(vector)

        logger.debug(
            "Сгенерирован эмбеддинг запроса через Yandex API, токенов {}",
            result.num_tokens,
        )
        embedding = vector.tolist()

        if self._cache:
            await self._cache.set(text, embedding)

        return embedding

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Синхронная версия генерации эмбеддингов."""
        return asyncio.run(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        """Синхронная версия генерации эмбеддинга."""
        return asyncio.run(self.aembed_query(text))
