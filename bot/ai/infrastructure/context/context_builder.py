from abc import ABC

from langchain_core.documents import Document


class ContextBuilder(ABC):
    async def build(self, docs: list[Document]) -> str:
        raise NotImplementedError


class SimpleContextBuilder(ContextBuilder):

    def __init__(self, max_chars: int = 3000):
        self.max_chars = max_chars

    async def build(self, docs: list[Document]) -> str:

        context_parts = []
        total = 0

        for doc in docs:

            text = f"[chunk {doc.metadata.get('chunk_id')}]\n{doc.page_content}"

            if total + len(text) > self.max_chars:
                break

            context_parts.append(text)
            total += len(text)

        return "\n\n".join(context_parts)
