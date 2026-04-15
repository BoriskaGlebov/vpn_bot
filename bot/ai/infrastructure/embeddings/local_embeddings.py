import asyncio
from collections.abc import Iterable

import numpy as np
from core.config import settings_ai
from langchain_core.embeddings import Embeddings
from loguru import logger


class LocalEmbeddings(Embeddings):
    """Сервис генерации эмбеддингов на базе SentenceTransformer.

    Используется для локальной генерации векторов без обращения к внешним API.

    Attributes
        _model (SentenceTransformer): Загруженная модель эмбеддингов.
        _normalize (bool): Признак L2-нормализации выходных векторов.

    """

    def __init__(
        self,
        model_name: str,
        normalize: bool = True,
    ) -> None:
        """Инициализирует модель эмбеддингов.

        Args:
            model_name: Имя модели SentenceTransformer.
            normalize: Выполнять ли L2-нормализацию эмбеддингов.

        """
        if settings_ai.skip_ai_init:
            raise RuntimeError("AI initialization skipped")

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._normalize = normalize

        logger.info(
            "LocalEmbeddings initialized | model={} normalize={}",
            model_name,
            normalize,
        )

    def _encode_sync(self, texts: Iterable[str]) -> np.ndarray:
        """Синхронная генерация эмбеддингов.

        Args:
            texts (Iterable[str]): Список текстов для кодирования.

        Returns
            np.ndarray: Массив эмбеддингов размерности (len(texts), dim).

        """
        embeddings = self._model.encode(
            list(texts),
            batch_size=32,
            show_progress_bar=False,
        )

        if self._normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            embeddings = embeddings / norms
            logger.debug("Эмбеддинги нормализованы по L2")

        return embeddings

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Асинхронная генерация эмбеддингов для списка документов.

        Args:
            texts (List[str]): Список текстов.

        Returns
            List[List[float]]: Список эмбеддингов.

        """
        embeddings = await asyncio.to_thread(self._encode_sync, texts)

        logger.info("Создано {} эмбеддингов для документов", len(texts))

        return embeddings.tolist()

    async def aembed_query(self, text: str) -> list[float]:
        """Асинхронная генерация эмбеддинга для одного запроса.

        Args:
            text (str): Текст запроса.

        Returns
            List[float]: Эмбеддинг запроса.

        """
        embedding = await asyncio.to_thread(self._encode_sync, [text])

        logger.debug("Эмбеддинг для запроса сгенерирован")

        return embedding[0].tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Синхронная версия генерации эмбеддингов документов."""
        return self._encode_sync(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        """Синхронная версия генерации эмбеддинга запроса."""
        return self._encode_sync([text])[0].tolist()
