from typing import Protocol


class BaseLLMProvider(Protocol):
    async def generate(self, context: str, question: str) -> str: ...
