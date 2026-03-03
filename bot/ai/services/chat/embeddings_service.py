import asyncio
from collections.abc import Iterable

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.schemas import SKnowledgeChunk, SKnowledgeChunkFilter
from bot.config import settings_ai
from bot.database import async_session


class EmbeddingService:
    """Сервис для генерации эмбеддингов текстов с использованием SentenceTransformer.

    Attributes
        _model (SentenceTransformer): Модель для генерации эмбеддингов.
        _normalize (bool): Флаг нормализации векторов по L2.

    """

    def __init__(
        self,
        model_name: str = settings_ai.model_llm_name,
        normalize: bool = settings_ai.normalize,
    ) -> None:
        """Инициализация EmbeddingService.

        Args:
            model_name (str): Название модели SentenceTransformer.
            normalize (bool): Нужно ли нормализовать эмбеддинги.

        """
        self._model = SentenceTransformer(model_name)
        self._normalize = normalize
        logger.info(
            "EmbeddingService инициализирована с моделью '{}' normalize={}",
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
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            logger.debug("Эмбеддинги нормализованы по L2")

        return embeddings

    async def encode_documents(self, texts: list[str]) -> list[list[float]]:
        """Асинхронная генерация эмбеддингов для списка документов.

        Args:
            texts (List[str]): Список текстов.

        Returns
            List[List[float]]: Список эмбеддингов.

        """
        embeddings = await asyncio.to_thread(self._encode_sync, texts)
        logger.info("Создано {} эмбеддингов для документов", len(texts))
        return embeddings.tolist()

    async def encode_query(self, text: str) -> list[float]:
        """Асинхронная генерация эмбеддинга для одного запроса.

        Args:
            text (str): Текст запроса.

        Returns
            List[float]: Эмбеддинг запроса.

        """
        embedding = await asyncio.to_thread(self._encode_sync, [text])
        logger.debug("Эмбеддинг для запроса сгенерирован")
        return embedding[0].tolist()


class KnowledgeBaseInitializer:
    """Инициализация базы знаний с эмбеддингами.

    Задачи:
        - Проверка наличия эмбеддингов в базе для источника.
        - Генерация эмбеддингов через EmbeddingService.
        - Сохранение эмбеддингов в базу через KnowledgeChunkDAO.
    """

    def __init__(
        self,
        emb_service: EmbeddingService,
        source: str = "dialog_messages.yaml",
        chunks: list[str | dict] = None,
    ):
        """Инициализация класса.

        Args:
            emb_service (EmbeddingService): Сервис генерации эмбеддингов.
            source (str): Источник текстов, используется в поле `source` в БД.
            chunks (List[Union[str, dict]]): Список текстов или словарей с ключом `content`.

        """
        self._emb_service = emb_service
        self._source = source
        self._chunks = chunks or settings_ai.common_chunks
        logger.info(
            "KnowledgeBaseInitializer инициализирована для источника '{}'", source
        )

    async def initialize(self) -> None:
        """Инициализация базы знаний.

        Логика:
            1. Проверяем, есть ли эмбеддинги для данного источника.
            2. Если есть — пропускаем.
            3. Если нет — генерируем и сохраняем эмбеддинги.

        """
        async with async_session() as session:
            logger.info("Проверка существующих эмбеддингов для '{}'", self._source)
            existing_count = await KnowledgeChunkDAO.count(
                session=session, filters=SKnowledgeChunkFilter(source=self._source)
            )
            if existing_count:
                logger.info(
                    "Эмбеддинги уже есть в базе: {}, пропускаем инициализацию",
                    existing_count,
                )
                return

            logger.info(
                "Начало генерации эмбеддингов для {} документов", len(self._chunks)
            )
            embeddings = await self._emb_service.encode_documents(
                texts=[
                    c["content"] if isinstance(c, dict) else str(c)
                    for c in self._chunks
                ]
            )

            chunks_to_save: list[SKnowledgeChunk] = []
            for text_obj, vector in zip(self._chunks, embeddings):
                try:
                    content = (
                        text_obj.get("content")
                        if isinstance(text_obj, dict)
                        else str(text_obj)
                    )

                    if vector is None or not np.isfinite(vector).all():
                        raise ValueError("Эмбеддинг содержит недопустимые значения")

                    chunks_to_save.append(
                        SKnowledgeChunk(
                            source=self._source, content=content, embedding=vector
                        )
                    )
                except Exception as e:
                    logger.error(
                        "Ошибка при генерации эмбеддинга для текста '{}': {}",
                        content[:50] if "content" in locals() else str(text_obj)[:50],
                        e,
                    )
                    continue

            await KnowledgeChunkDAO.add_many(session=session, instances=chunks_to_save)
            await session.commit()
            logger.info(
                "Создано и сохранено {} эмбеддингов для источника '{}'",
                len(chunks_to_save),
                self._source,
            )
