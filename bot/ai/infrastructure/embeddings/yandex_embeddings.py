import asyncio

import numpy as np
from langchain_core.embeddings import Embeddings
from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio


class YandexEmbeddings(Embeddings):
    """Генерация эмбеддингов через Yandex AI Studio (асинхронно)."""

    def __init__(
        self,
        folder_id: str,
        api_key: str,
        normalize: bool = True,
    ) -> None:
        """Инициализация класса.

        Args:
            normalize (bool): Флаг нормализации векторов по L2.
            folder_id (str): Идентификатор папки в Yandex AI Studio.
            api_key (str): API-ключ для Yandex AI Studio.


        """
        self._normalize = normalize
        self._sdk = AsyncAIStudio(folder_id=folder_id, auth=api_key)
        self._model = self._sdk.models.text_embeddings("text-search-query")
        logger.info("YandexEmbeddings инициализирована с моделью 'query'")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Генерация эмбеддингов для списка текстов через Yandex API.

        Args:
            texts (List[str]): Список текстов.

        Returns
            List[List[float]]: Список эмбеддингов.

        """
        coros = [self._model.run(text) for text in texts]
        results = await asyncio.gather(*coros)

        vectors = np.array([r.embedding for r in results])

        if self._normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / norms
        logger.info("Сгенерировано {} эмбеддингов через Yandex API", len(vectors))
        return vectors.tolist()

    async def embed_query(self, text: str) -> list[float]:
        """Генерация эмбеддинга для одного запроса через Yandex API.

        Args:
            text (str): Текст запроса.

        Returns
            List[float]: Эмбеддинг запроса.

        """
        result = await self._model.run(text)
        logger.debug(f"tokens: {result.num_tokens}")
        vector = np.array(result.embedding)

        if self._normalize:
            vector = vector / np.linalg.norm(vector)

        logger.debug(
            "Сгенерирован эмбеддинг запроса через Yandex API, токенов {}",
            result.num_tokens,
        )
        return vector.tolist()
