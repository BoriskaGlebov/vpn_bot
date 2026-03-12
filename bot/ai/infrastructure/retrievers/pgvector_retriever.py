from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.ai.dao import KnowledgeChunkDAO


class PgVectorRetriever:

    def __init__(
        self,
        embeddings: Embeddings,
        session_factory: async_sessionmaker[AsyncSession],
        top_k: int = 5,
    ) -> None:
        self._embeddings = embeddings
        self._session_factory = session_factory
        self._top_k = top_k

    async def aretrieve(
        self,
        question: str,
    ) -> list[Document]:
        """Получение релевантных документов для вопроса."""

        try:
            query_vector = await self._embeddings.aembed_query(question)
        except Exception:
            logger.exception("Ошибка при генерации эмбеддинга вопроса")
            raise

        try:
            async with self._session_factory() as session:
                chunks = await KnowledgeChunkDAO.search_by_embedding(
                    session=session,
                    query_vector=query_vector,
                    top_k=self._top_k,
                    threshold=0.5,
                )
        except Exception:
            logger.exception("Ошибка при поиске документов")
            raise

        documents: list[Document] = []

        for chunk in chunks:
            documents.append(
                Document(
                    page_content=chunk.content,
                    metadata={
                        "source": chunk.source,
                        "chunk_id": chunk.id,
                    },
                )
            )

        logger.debug("Retriever вернул {} документов", len(documents))

        return documents
