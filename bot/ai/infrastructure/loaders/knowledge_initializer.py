from typing import Any

import numpy as np
from langchain_core.embeddings import Embeddings
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.schemas import SKnowledgeChunk, SKnowledgeChunkFilter
from bot.app_error.base_error import AppError
from bot.config import settings_ai
from bot.database import async_session


class KnowledgeBaseInitializer:
    """Инициализация базы знаний с эмбеддингами.

    Проверяет наличие эмбеддингов в базе, генерирует недостающие и сохраняет их.
    """

    def __init__(
        self,
        emb_service: Embeddings,
        source: str = "dialog_messages.yaml",
        chunks: list[str | dict[str, str]] | None = None,
        session_factory: async_sessionmaker[AsyncSession | Any] = async_session,
    ) -> None:
        """Инициализация класса.

        Args:
            emb_service (Embeddings): Сервис генерации эмбеддингов.
            source (str): Источник текстов, используется в поле `source` в БД.
            chunks (List[Union[str, dict]]): Список текстов или словарей с ключом `content`.
            session_factory (async_sessionmaker[AsyncSession | Any]): Фабрика асинхронных сессий SQLAlchemy.

        """
        self._emb_service = emb_service
        self._source = source
        self._chunks = chunks or settings_ai.common_chunks
        self._session_factory = session_factory
        logger.info(
            "KnowledgeBaseInitializer инициализирована для источника '{}'", source
        )

    async def initialize(self) -> None:
        """Инициализация базы знаний.

        Проверяет наличие эмбеддингов для источника и создает недостающие.

        Raises
            AppError: Если эмбеддинг содержит недопустимые значения.

        """
        async with self._session_factory() as session:
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
            embeddings = await self._emb_service.aembed_documents(
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
