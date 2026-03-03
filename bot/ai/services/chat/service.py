from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.services.chat.base import BaseLLMProvider
from bot.ai.services.chat.embeddings_service import EmbeddingService


class ChatService:
    """Сервис для общения пользователя с LLM на основе базы знаний.

    Логика:
        1. Проверка минимальной длины вопроса.
        2. Генерация эмбеддинга вопроса.
        3. Поиск релевантных документов в базе по эмбеддингу.
        4. Формирование контекста для LLM с ограничением по длине.
        5. Генерация ответа через LLM.

    """

    def __init__(self, llm: BaseLLMProvider, emb_service: EmbeddingService) -> None:
        """Инициализация класса.

        Args:
            llm (BaseLLMProvider): Провайдер LLM для генерации ответов.
            emb_service (EmbeddingService): Сервис для генерации эмбеддингов.

        """
        self._llm = llm
        self._emb_service = emb_service

    async def ask(
        self, question: str, session: AsyncSession, max_context_chars: int = 2000
    ) -> str:
        """Обрабатывает вопрос пользователя и возвращает ответ на основе базы знаний.

        Args:
            question (str): Вопрос пользователя.
            session (AsyncSession): Асинхронная сессия SQLAlchemy для поиска документов.
            max_context_chars (int, optional): Максимальная длина контекста для LLM. Defaults to 2000.

        Returns
            str: Ответ на вопрос.

        """
        # Проверка минимальной длины
        if len(question.split()) < 3:
            logger.info("Вопрос слишком короткий: '{}'", question)
            return "Напишите подробнее, не могу понять что вы хотите."

        logger.info("Начало обработки вопроса: '{}'", question[:50])

        logger.debug("1. Генерация вектора вопроса")
        try:
            q_vector: list[float] = await self._emb_service.encode_query(question)
        except Exception as e:
            logger.exception("Ошибка при генерации эмбеддинга вопроса: {}", e)
            return "Произошла ошибка при обработке вашего вопроса."

        logger.debug("Вектор вопроса сгенерирован (длина {})", len(q_vector))

        logger.debug("2. Поиск релевантных документов в базе")
        try:
            docs = await KnowledgeChunkDAO.search_by_embedding(
                session=session,
                query_vector=q_vector,
                top_k=5,
                threshold=0.6,
            )
        except Exception as e:
            logger.exception("Ошибка при поиске документов: {}", e)
            return "Не удалось найти релевантные документы."

        logger.info("Найдено {} релевантных документов", len(docs))

        if not docs:
            return "Извините, по этой теме информации нет."

        context_pieces: list[str] = []
        total_chars = 0
        for doc in docs:
            piece = doc.content.strip()
            if total_chars + len(piece) > max_context_chars:
                remaining = max_context_chars - total_chars
                if remaining > 0:
                    context_pieces.append(piece[:remaining])
                    total_chars += remaining
                break
            context_pieces.append(piece)
            total_chars += len(piece)

        context = "\n\n".join(context_pieces)
        logger.debug("Длина контекста для LLM: {} символов", len(context))

        try:
            answer = await self._llm.generate(context=context, question=question)
            if not answer.strip():
                logger.warning("LLM вернул пустой ответ")
                return "Не удалось сгенерировать ответ по контексту."
            logger.info("Ответ сгенерирован успешно ({} символов)", len(answer))
            return answer
        except Exception as e:
            logger.exception("Ошибка при генерации ответа LLM: {}", e)
            return "Произошла ошибка при генерации ответа."
