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

    def _is_valid_question(self, question: str) -> bool:
        """Проверка минимальной длины вопроса."""
        if len(question.split()) < 3:
            logger.info("Вопрос слишком короткий: '{}'", question)
            return False
        return True

    async def _get_base_context(
        self, question: str, session: AsyncSession, max_context_chars: int
    ) -> str:
        """Поиск релевантных документов и формирование контекста базы знаний."""
        try:
            q_vector = await self._emb_service.encode_query(question)
        except Exception as e:
            logger.exception("Ошибка при генерации эмбеддинга вопроса: {}", e)
            return ""

        try:
            docs = await KnowledgeChunkDAO.search_by_embedding(
                session=session, query_vector=q_vector, top_k=5, threshold=0.6
            )
        except Exception as e:
            logger.exception("Ошибка при поиске документов: {}", e)
            raise

        context_pieces = []
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

        return "\n\n".join(context_pieces)

    def _merge_context(self, base_context: str, user_context: list[str] | None) -> str:
        """Объединяет контекст базы с историей пользователя."""
        if not user_context:
            return base_context
        history_text = "Предыдущие вопросы от пользователя" + "\n".join(user_context)
        if base_context:
            return f"{history_text}\n\nДанные из базы знаний: {base_context}"
        return history_text

    async def _generate_answer(self, question: str, context: str) -> str:
        """Генерация ответа через LLM."""
        try:
            answer = await self._llm.generate(context=context, question=question)
            if not answer.strip():
                logger.warning("LLM вернул пустой ответ")
                return "Не удалось сгенерировать ответ по контексту."
            return answer
        except Exception as e:
            logger.exception("Ошибка при генерации ответа LLM: {}", e)
            raise

    async def ask(
        self,
        question: str,
        session: AsyncSession,
        user_context: list[str] | None = None,
        max_context_chars: int = 2000,
    ) -> str:
        """Основной метод: отвечает на вопрос пользователя с учетом истории."""
        if not self._is_valid_question(question):
            return "Напишите подробнее, не могу понять что вы хотите."
        base_context = await self._get_base_context(
            question, session, max_context_chars
        )
        full_context = self._merge_context(base_context, user_context)
        return await self._generate_answer(question, full_context)
