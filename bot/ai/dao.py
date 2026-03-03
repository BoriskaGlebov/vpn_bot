from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.models import KnowledgeChunk
from bot.dao.base import BaseDAO


class KnowledgeChunkDAO(BaseDAO[KnowledgeChunk]):
    """DAO для работы с моделью KnowledgeChunk."""

    model = KnowledgeChunk

    @classmethod
    async def search_by_embedding(
        cls,
        session: AsyncSession,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float = 0.2,
    ) -> list[KnowledgeChunk]:
        """Поиск документов по косинусной близости эмбеддингов.

        Метод выполняет поиск ближайших документов в базе по вектору запроса,
        сортирует по расстоянию и фильтрует результаты по порогу схожести.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            query_vector (List[float]): Вектор запроса.
            top_k (int, optional): Сколько ближайших документов вернуть. Defaults to 5.
            threshold (float, optional): Порог косинусного расстояния для фильтрации.
                                         Чем меньше — тем ближе. Defaults to 0.2.

        Returns
            List[KnowledgeChunk]: Список объектов KnowledgeChunk, которые прошли фильтр.

        Raises
            ValueError: Если query_vector пустой или содержит недопустимые значения.

        """
        if not query_vector or not all(
            isinstance(x, (int, float)) for x in query_vector
        ):
            raise ValueError("query_vector должен быть непустым списком чисел")
        try:
            query = (
                select(
                    cls.model,
                    cls.model.embedding.cosine_distance(query_vector).label("distance"),
                )
                .order_by(cls.model.embedding.cosine_distance(query_vector))
                .limit(top_k)
            )

            result = await session.execute(query)
            rows = result.all()

            for doc, dist in rows:
                logger.debug(
                    "Найден документ: '{}...', distance={:.3f}", doc.content[:50], dist
                )

            logger.info("Найдено {} документов для запроса", len(rows))
            filtered: list[KnowledgeChunk] = []
            for row in rows:
                doc, dist = row
                if dist is None or not isinstance(dist, (int, float)):
                    logger.warning(
                        "Пропущен документ с некорректным distance: {} (source={})",
                        dist,
                        getattr(doc, "source", "<unknown>"),
                    )
                    continue
                if dist < threshold:
                    filtered.append(doc)

            logger.info("После фильтрации осталось {} документов", len(filtered))
            return filtered
        except Exception as e:
            logger.exception("Ошибка при поиске по эмбеддингам: {}", e)
            return []
