from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.ai.dao import KnowledgeChunkDAO


class PgVectorRetriever:
    """Класс для извлечения релевантных документов из базы знаний с помощью эмбеддингов.

    Используется для RAG-подхода: преобразует вопрос в вектор, ищет ближайшие
    chunk'и в базе и возвращает их как список Document для LangChain.

    Attributes
        _embeddings (Embeddings): Сервис генерации эмбеддингов.
        _session_factory (async_sessionmaker[AsyncSession]): Фабрика асинхронных сессий SQLAlchemy.
        _top_k (int): Количество ближайших документов для извлечения.

    """

    def __init__(
        self,
        embeddings: Embeddings,
        session_factory: async_sessionmaker[AsyncSession],
        threshold: float = 0.5,
        top_k: int = 5,
    ) -> None:
        """Инициализация ретривера.

        Args:
            embeddings: Экземпляр Embeddings для генерации векторов.
            session_factory: Фабрика асинхронных сессий SQLAlchemy.
            top_k: Количество ближайших документов для извлечения.
            threshold: Порог косинусного расстояния для фильтрации.
                                      Чем меньше — тем ближе.

        """
        self._embeddings = embeddings
        self._session_factory = session_factory
        self._top_k = top_k
        self._threshold = threshold

    async def aretrieve(
        self,
        question: str,
    ) -> list[Document]:
        """Извлечение релевантных документов для вопроса.

        Логика:
            1. Генерация вектора эмбеддинга для вопроса.
            2. Поиск ближайших chunk'ов в базе данных через KnowledgeChunkDAO.
            3. Преобразование найденных chunk'ов в объекты Document LangChain.

        Args:
            question (str): Вопрос пользователя.

        Returns
            List[Document]: Список документов, каждый с полями page_content и metadata.

        Raises
            Exception: Если произошла ошибка при генерации эмбеддинга или запросе к базе.

        """
        try:
            query_vector = await self._embeddings.aembed_query(question)
            logger.debug("Сгенерирован эмбеддинг для вопроса: '{}'", question[:50])
        except Exception:
            logger.exception("Ошибка при генерации эмбеддинга вопроса")
            raise

        try:
            async with self._session_factory() as session:
                chunks = await KnowledgeChunkDAO.search_by_embedding(
                    session=session,
                    query_vector=query_vector,
                    top_k=self._top_k,
                    threshold=self._threshold,
                )
                logger.debug("Найдено {} релевантных chunk'ов", len(chunks))
        except Exception:
            logger.exception("Ошибка при поиске документов")
            raise

        documents: list[Document] = [
            Document(
                page_content=chunk.content,
                metadata={
                    "source": chunk.source,
                    "chunk_id": chunk.id,
                },
            )
            for chunk in chunks
        ]

        logger.debug("Retriever вернул {} документов", len(documents))

        return documents
