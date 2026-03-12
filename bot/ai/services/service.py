from loguru import logger

from bot.ai.infrastructure.chains.rag_chain import RAGChain
from bot.ai.infrastructure.context.context_builder import SimpleContextBuilder
from bot.ai.infrastructure.embeddings.factory_embeddings import EmbeddingsFactory
from bot.ai.infrastructure.llm.yandex_llm import YandexChatModel
from bot.ai.infrastructure.loaders.knowledge_initializer import KnowledgeBaseInitializer
from bot.ai.infrastructure.retrievers.pgvector_retriever import PgVectorRetriever
from bot.database import async_session


class ChatService:

    def __init__(self, rag_chain):
        self._rag_chain = rag_chain

    def _is_valid_question(self, question: str) -> bool:
        if len(question.split()) < 3:
            logger.info("Вопрос слишком короткий: '{}'", question)
            return False
        return True

    async def ask(self, question: str) -> str:

        if not self._is_valid_question(question):
            return "Напишите подробнее, не могу понять что вы хотите."

        try:
            answer = await self._rag_chain.run(question)
            return answer
        except Exception:
            logger.exception("Ошибка при работе RAG pipeline")
            raise


async def build_chat_service():
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

    return ChatService(rag_chain)
