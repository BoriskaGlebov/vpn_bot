from typing import Protocol


class BaseLLMProvider(Protocol):
    async def generate(self, prompt: str) -> str: ...
