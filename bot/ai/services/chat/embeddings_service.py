import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterable

import numpy as np
from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.schemas import SKnowledgeChunk, SKnowledgeChunkFilter
from bot.app_error.base_error import AppError
from bot.config import settings_ai
from bot.database import async_session

if not settings_ai.skip_ai_init:
    from sentence_transformers import SentenceTransformer


class BaseEmbeddingService(ABC):
    """Абстрактный базовый класс для генерации эмбеддингов."""

    def __init__(self, normalize: bool) -> None:
        """Инициализация класса.

        Args:
            normalize (bool): Флаг для L2-нормализации эмбеддингов.

        """
        self._normalize = normalize

    @abstractmethod
    async def encode_documents(self, texts: list[str]) -> list[list[float]]:
        """Генерация эмбеддингов для списка документов.

        Args:
            texts (List[str]): Список текстов.

        Returns
            List[List[float]]: Список эмбеддингов.

        """
        ...

    @abstractmethod
    async def encode_query(self, text: str) -> list[float]:
        """Генерация эмбеддинга для одного запроса.

        Args:
            text (str): Текст запроса.

        Returns
            List[float]: Эмбеддинг запроса.

        """
        ...


class YandexEmbeddingService(BaseEmbeddingService):
    """Генерация эмбеддингов через Yandex AI Studio (асинхронно)."""

    def __init__(self, normalize: bool, folder_id: str, api_key: str) -> None:
        """Инициализация класса.

        Args:
            normalize (bool): Флаг нормализации векторов по L2.
            folder_id (str): Идентификатор папки в Yandex AI Studio.
            api_key (str): API-ключ для Yandex AI Studio.


        """
        super().__init__(normalize)
        self._sdk = AsyncAIStudio(folder_id=folder_id, auth=api_key)
        self._model = self._sdk.models.text_embeddings("text-search-query")
        logger.info("YandexEmbeddingService инициализирована с моделью 'query'")

    async def encode_documents(self, texts: list[str]) -> list[list[float]]:
        """Генерация эмбеддингов для списка текстов через Yandex API.

        Args:
            texts (List[str]): Список текстов.

        Returns
            List[List[float]]: Список эмбеддингов.

        """
        coros = [self._model.run(text) for text in texts]
        results = await asyncio.gather(*coros)
        embeddings = np.array([r.embedding for r in results])
        if self._normalize:
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        logger.info("Сгенерировано {} эмбеддингов через Yandex API", len(embeddings))
        return embeddings.tolist()

    async def encode_query(self, text: str) -> list[float]:
        """Генерация эмбеддинга для одного запроса через Yandex API.

        Args:
            text (str): Текст запроса.

        Returns
            List[float]: Эмбеддинг запроса.

        """
        result = await self._model.run(text)
        embedding = np.array(result.embedding)

        if self._normalize:
            embedding = embedding / np.linalg.norm(embedding)

        logger.debug(
            "Сгенерирован эмбеддинг запроса через Yandex API, токенов {}",
            result.num_tokens,
        )

        return embedding.tolist()


class EmbeddingService(BaseEmbeddingService):
    """Сервис для генерации эмбеддингов текстов с использованием SentenceTransformer.

    Attributes
        _model (SentenceTransformer): Модель для генерации эмбеддингов.
        _normalize (bool): Флаг нормализации векторов по L2.

    """

    def __init__(
        self,
        model_name: str = (
            settings_ai.model_llm_name if settings_ai.model_llm_name else "model_name"
        ),
        normalize: bool = settings_ai.normalize,
    ) -> None:
        """Инициализация EmbeddingService.

        Args:
            model_name (str): Название модели SentenceTransformer.
            normalize (bool): Нужно ли нормализовать эмбеддинги.

        """
        super().__init__(normalize)
        self._model = SentenceTransformer(model_name)
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


class EmbeddingServiceFactory:
    """Фабрика для выбора локального или Yandex EmbeddingService."""

    @staticmethod
    def create() -> EmbeddingService | YandexEmbeddingService:
        """Возвращает сервис генерации эмбеддингов в зависимости от окружения."""
        if settings_ai.skip_ai_init:
            logger.info("Используем YandexEmbeddingService для PROD")
            return YandexEmbeddingService(
                normalize=settings_ai.normalize,
                folder_id=settings_ai.yandex_folder_id,
                api_key=settings_ai.secret_key_ai.get_secret_value(),
            )
        else:
            logger.info("Используем локальный EmbeddingService для DEV")
            return EmbeddingService()


class KnowledgeBaseInitializer:
    """Инициализация базы знаний с эмбеддингами.

    Задачи:
        - Проверка наличия эмбеддингов в базе для источника.
        - Генерация эмбеддингов через EmbeddingService.
        - Сохранение эмбеддингов в базу через KnowledgeChunkDAO.
    """

    def __init__(
        self,
        emb_service: BaseEmbeddingService,
        source: str = "dialog_messages.yaml",
        chunks: list[str | dict[str, str]] | None = None,
    ) -> None:
        """Инициализация класса.

        Args:
            emb_service (BaseEmbeddingService): Сервис генерации эмбеддингов.
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
                    if isinstance(text_obj, dict):
                        content: str = str(text_obj.get("content", ""))
                    else:
                        content = str(text_obj)

                    if vector is None or not np.isfinite(vector).all():
                        raise AppError("Эмбеддинг содержит недопустимые значения")

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
