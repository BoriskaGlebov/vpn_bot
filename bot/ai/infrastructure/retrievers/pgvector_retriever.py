from ai.dao import KnowledgeChunkDAO
from langchain_core.embeddings import Embeddings
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


class PgVectorRetriever:

    def __init__(self, embeddings: Embeddings):
        self._embeddings = embeddings

    async def retrieve(self, question: str, session: AsyncSession) -> str:
        try:
            query_vector = await self._embeddings.aembed_query(question)
        except Exception as e:
            logger.exception("Ошибка при генерации эмбеддинга вопроса: {}", e)
            raise
        try:
            chunks = await KnowledgeChunkDAO.search_by_embedding(
                session=session, query_vector=query_vector, top_k=5, threshold=0.6
            )
        except Exception as e:
            logger.exception("Ошибка при поиске документов: {}", e)
            raise

        return "\n\n".join(chunk.content for chunk in chunks)
