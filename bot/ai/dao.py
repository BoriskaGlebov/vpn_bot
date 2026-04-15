from collections.abc import Sequence

from core.dao.base import BaseDAO
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.models import KnowledgeChunk


class KnowledgeChunkDAO(BaseDAO[KnowledgeChunk]):
    """DAO для работы с моделью KnowledgeChunk."""

    model = KnowledgeChunk

    @classmethod
    async def search_by_embedding(
        cls,
        session: AsyncSession,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float | None = None,
    ) -> Sequence[KnowledgeChunk]:
        """Поиск документов по косинусной близости эмбеддингов.

        Метод выполняет поиск ближайших документов в базе по вектору запроса,
        сортирует по расстоянию и фильтрует результаты по порогу схожести.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            query_vector (List[float]): Вектор запроса.
            top_k (int, optional): Сколько ближайших документов вернуть. Defaults to 5.
            threshold (float, optional): Порог косинусного расстояния для фильтрации.
                                         Чем меньше — тем ближе. Опционально.

        Returns
            List[KnowledgeChunk]: Список объектов KnowledgeChunk, которые прошли фильтр.

        Raises
            ValueError: Если query_vector пустой или содержит недопустимые значения.

        """
        if not query_vector or not all(
            isinstance(x, int | float) for x in query_vector
        ):
            raise ValueError("query_vector должен быть непустым списком чисел")
        try:
            distance = cls.model.embedding.cosine_distance(query_vector)
            stmt = (
                select(cls.model, distance.label("distance"))
                .order_by(distance)
                .limit(top_k)
            )
            if threshold is not None:
                stmt = stmt.where(distance < threshold)
            result = await session.execute(stmt)
            rows = result.all()
            chunks = []

            logger.info("Найдено {} чанков", len(rows))

            for chunk, dist in rows:
                logger.info(
                    "chunk id={} source={} distance={:.4f}",
                    chunk.id,
                    chunk.source,
                    dist,
                )

                logger.debug(
                    "text='{}...'",
                    chunk.content[:80],
                )

                chunks.append(chunk)

            return chunks
        except Exception as e:
            logger.exception("Ошибка при поиске по эмбеддингам: {}", e)
            raise
