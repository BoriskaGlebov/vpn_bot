from bot.ai.services.chat.base import BaseLLMProvider
from bot.ai.services.chat.embeddings_service import EmbeddingService


class ChatService:
    def __init__(self, llm: BaseLLMProvider, emb_service: EmbeddingService) -> None:
        self._llm = llm
        self._emb_service = emb_service

    async def ask(self, question: str) -> str:
        return await self._llm.generate(question)
