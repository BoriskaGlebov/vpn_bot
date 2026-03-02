import asyncio
from typing import Iterable, List

import numpy as np
from sentence_transformers import SentenceTransformer

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.schemas import SKnowledgeChunk, SKnowledgeChunkFilter
from bot.config import settings_ai
from bot.database import async_session


class EmbeddingService:
    def __init__(
        self,
        model_name: str = settings_ai.model_llm_name,
        normalize: bool = settings_ai.normalize,
    ) -> None:
        self._model = SentenceTransformer(model_name)
        self._normalize = normalize

    def _encode_sync(self, texts: Iterable[str]) -> np.ndarray:
        embeddings = self._model.encode(
            list(texts),
            batch_size=32,
            show_progress_bar=False,
        )

        if self._normalize:
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        return embeddings

    async def encode_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = await asyncio.to_thread(self._encode_sync, texts)
        return embeddings.tolist()

    async def encode_query(self, text: str) -> List[float]:
        embedding = await asyncio.to_thread(self._encode_sync, [text])
        return embedding[0].tolist()


class KnowledgeBaseInitializer:
    """
    Класс для инициализации базы знаний:
    - проверяет наличие эмбеддингов в БД,
    - создаёт их через EmbeddingService, если их нет,
    - сохраняет в базу через KnowledgeChunkDAO.
    """

    def __init__(
        self, emb_service: EmbeddingService, source: str = "dialog_messages.yaml"
    ):
        self._emb_service = emb_service
        self._source = source

    async def initialize(self) -> None:
        """Создаёт эмбеддинги документации и сохраняет их в БД, если их ещё нет."""
        async with async_session() as session:
            # Проверяем, есть ли уже эмбеддинги для данного источника
            existing_count = await KnowledgeChunkDAO.count(
                session=session, filters=SKnowledgeChunkFilter(source=self._source)
            )
            if existing_count:
                print("Эмбеддинги уже есть в базе, пропускаем инициализацию")
                return

            # Генерируем эмбеддинги для всех документов/чанков
            embeddings = await self._emb_service.encode_documents(
                texts=settings_ai.common_chunks
            )

            chunks_to_save = []
            for text, vector in zip(settings_ai.common_chunks, embeddings):
                # Если текст может быть словарём с ключом 'content'
                content = text.get("content") if isinstance(text, dict) else str(text)
                chunks_to_save.append(
                    SKnowledgeChunk(
                        source=self._source, content=content, embedding=vector
                    )
                )

            # Сохраняем все в базу
            await KnowledgeChunkDAO.add_many(session=session, instances=chunks_to_save)
            await session.commit()
            print(f"Создано и сохранено {len(chunks_to_save)} эмбеддингов")
