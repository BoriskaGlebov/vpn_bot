import numpy as np
from ai.dao import KnowledgeChunkDAO
from ai.schemas import SKnowledgeChunk, SKnowledgeChunkFilter
from app_error.base_error import AppError
from config import settings_ai
from database import async_session
from langchain_core.embeddings import Embeddings
from loguru import logger


class KnowledgeBaseInitializer:
    """Инициализация базы знаний с эмбеддингами.

    Задачи:
        - Проверка наличия эмбеддингов в базе для источника.
        - Генерация эмбеддингов через EmbeddingService.
        - Сохранение эмбеддингов в базу через KnowledgeChunkDAO.
    """

    def __init__(
        self,
        emb_service: Embeddings,
        source: str = "dialog_messages.yaml",
        chunks: list[str | dict[str, str]] | None = None,
    ) -> None:
        """Инициализация класса.

        Args:
            emb_service (Embeddings): Сервис генерации эмбеддингов.
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
