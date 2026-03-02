from .base import BaseLLMProvider


class ChatService:
    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm

    async def ask(self, question: str) -> str:
        return await self._llm.generate(question)
