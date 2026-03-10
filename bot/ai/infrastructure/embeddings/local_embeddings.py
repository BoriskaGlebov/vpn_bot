import asyncio
from collections.abc import Iterable

import numpy as np
from config import settings_ai
from langchain_core.embeddings import Embeddings
from loguru import logger
from sentence_transformers import SentenceTransformer


class LocalEmbeddings(Embeddings):
    """Embedding сервис на базе SentenceTransformer для LangChain."""

    def __init__(
        self,
        model_name: str,
        normalize: bool = True,
    ) -> None:
        self._model = SentenceTransformer(model_name)
        self._normalize = normalize

        logger.info(
            "LocalEmbeddings initialized with model '{}' normalize={}",
            model_name,
            normalize,
        )

    def _encode_sync(self, texts: Iterable[str]) -> np.ndarray:
        """Синхронная генерация эмбеддингов."""

        embeddings = self._model.encode(
            list(texts),
            batch_size=32,
            show_progress_bar=False,
        )

        if self._normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            embeddings = embeddings / norms
            logger.debug("Embeddings normalized (L2)")

        return embeddings

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Асинхронная генерация эмбеддингов документов."""

        embeddings = await asyncio.to_thread(self._encode_sync, texts)

        logger.info("Generated {} embeddings for documents", len(texts))

        return embeddings.tolist()

    async def aembed_query(self, text: str) -> list[float]:
        """Асинхронная генерация эмбеддинга запроса."""

        embedding = await asyncio.to_thread(self._encode_sync, [text])

        logger.debug("Query embedding generated")

        return embedding[0].tolist()

    # sync методы (fallback для LangChain)
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode_sync(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._encode_sync([text])[0].tolist()


if __name__ == "__main__":

    async def main():
        embeddings = LocalEmbeddings(model_name=settings_ai.model_llm_name)
        res = await embeddings.aembed_query("Привет")
        print(res)

    asyncio.run(main())
