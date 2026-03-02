from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.models import KnowledgeChunk
from bot.dao.base import BaseDAO


class KnowledgeChunkDAO(BaseDAO[KnowledgeChunk]):
    model = KnowledgeChunk

    @classmethod
    async def search_by_embedding(
        cls,
        session: AsyncSession,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float = 0.2,
    ):
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
            print(f"Distance={dist:.3f}, content={doc.content[:50]}...")

        # Фильтруем по порогу похожести
        filtered = [
            row[0] for row in rows if row[1] < threshold
        ]  # чем меньше, тем ближе
        return filtered
