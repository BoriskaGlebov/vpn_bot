from core.database import async_session
from loguru import logger

from bot.ai.infrastructure.chains.rag_chain import RAGChain
from bot.ai.infrastructure.context.context_builder import SimpleContextBuilder
from bot.ai.infrastructure.embeddings.factory_embeddings import EmbeddingsFactory
from bot.ai.infrastructure.llm.yandex_llm import YandexChatModel
from bot.ai.infrastructure.loaders.knowledge_initializer import KnowledgeBaseInitializer
from bot.ai.infrastructure.retrievers.pgvector_retriever import PgVectorRetriever


class ChatService:
    """Сервис обработки пользовательских вопросов через RAG pipeline.

    Логика:
        1. Проверка валидности вопроса.
        2. Генерация ответа через RAGChain.
        3. Обработка ошибок и логирование.

    Attributes
        _rag_chain (RAGChain): RAG цепочка для поиска контекста и генерации ответа.

    """

    def __init__(self, rag_chain: RAGChain) -> None:
        """Инициализация ChatService.

        Args:
            rag_chain (RAGChain): RAG цепочка.

        """
        self._rag_chain = rag_chain
        logger.info("ChatService инициализирован")

    def _is_valid_question(self, question: str) -> bool:
        """Проверяет валидность вопроса пользователя.

        Условия:
            - Вопрос должен содержать минимум 3 слова.

        Args:
            question (str): Текст вопроса.

        Returns
            bool: True если вопрос валиден, иначе False.

        """
        if len(question.split()) < 3:
            logger.info("Вопрос слишком короткий: '{}'", question)
            return False
        return True

    async def ask(self, question: str) -> str:
        """Обрабатывает вопрос и возвращает ответ.

        Args:
            question (str): Вопрос пользователя.

        Returns
            str: Ответ от RAGChain или подсказка при невалидном вопросе.

        Raises
            Exception: Пробрасывает любые ошибки RAGChain после логирования.

        """
        if not self._is_valid_question(question):
            return "Напишите подробнее, не могу понять что вы хотите."

        logger.info("Получен вопрос: '{}'", question[:100])

        import time

        start_time = time.perf_counter()

        try:
            answer = await self._rag_chain.run(question)
        except Exception:
            logger.exception("Ошибка при работе RAG pipeline")
            raise
        finally:
            elapsed = time.perf_counter() - start_time
            logger.info("Обработка вопроса завершена за {:.3f} секунд", elapsed)

        logger.debug(
            "Сгенерирован ответ (первые 100 символов): {}",
            answer[:100] + ("..." if len(answer) > 100 else ""),
        )

        return answer


async def build_chat_service() -> ChatService:
    """Фабрика для построения и инициализации ChatService.

    Шаги:
        1. Создание Embeddings через фабрику.
        2. Инициализация KnowledgeBase (с генерацией эмбеддингов, если необходимо).
        3. Создание Retriever и ContextBuilder.
        4. Создание LLM и RAGChain.
        5. Возврат готового ChatService.

    Returns
        ChatService: Инициализированный сервис для общения.

    """
    logger.info("Начало сборки ChatService")

    emb = EmbeddingsFactory().create()
    knowledge_initializer = KnowledgeBaseInitializer(emb_service=emb)
    await knowledge_initializer.initialize()

    retriever = PgVectorRetriever(embeddings=emb, session_factory=async_session)
    context_builder = SimpleContextBuilder()
    llm = YandexChatModel()

    rag_chain = RAGChain(
        llm=llm,
        retriever=retriever,
        context_builder=context_builder,
    )

    logger.info("ChatService успешно собран")
    return ChatService(rag_chain)
