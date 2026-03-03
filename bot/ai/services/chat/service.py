from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.services.chat.base import BaseLLMProvider
from bot.ai.services.chat.embeddings_service import EmbeddingService


class ChatService:
    def __init__(self, llm: BaseLLMProvider, emb_service: EmbeddingService) -> None:
        self._llm = llm
        self._emb_service = emb_service

    async def ask(self, question: str, session: AsyncSession) -> str:
        if len(question.split()) < 3:
            return "Напишите подробнее, не могу понять что вы хотите."
        print("1. Получаем вектор вопроса")
        q_vector = await self._emb_service.encode_query(question)
        print(len(q_vector))
        print("---" * 30)
        print("2. Ищем релевантные документы")
        docs = await KnowledgeChunkDAO.search_by_embedding(
            session, q_vector, top_k=5, threshold=0.6
        )
        print(docs)
        print("---" * 30)

        if not docs:
            return "Извините, по этой теме информации нет."

        context = "\n\n".join([d.content for d in docs])
        return await self._llm.generate(
            context=context,
            question=question,
        )
