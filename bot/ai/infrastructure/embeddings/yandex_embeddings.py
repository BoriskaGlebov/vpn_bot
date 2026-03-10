import asyncio

import numpy as np
from config import settings_ai
from langchain_core.embeddings import Embeddings
from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio


class YandexEmbeddings(Embeddings):

    def __init__(
        self,
        folder_id: str,
        api_key: str,
        normalize: bool = True,
    ):
        self._normalize = normalize
        self._sdk = AsyncAIStudio(folder_id=folder_id, auth=api_key)
        self._model = self._sdk.models.text_embeddings("text-search-query")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        coros = [self._model.run(text) for text in texts]
        results = await asyncio.gather(*coros)

        vectors = np.array([r.embedding for r in results])

        if self._normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / norms

        return vectors.tolist()

    async def embed_query(self, text: str) -> list[float]:
        result = await self._model.run(text)
        logger.debug(f"tokens: {result.num_tokens}")
        vector = np.array(result.embedding)

        if self._normalize:
            vector = vector / np.linalg.norm(vector)

        return vector.tolist()


if __name__ == "__main__":

    async def main():
        embeddings = YandexEmbeddings(
            folder_id=settings_ai.yandex_folder_id,
            api_key=settings_ai.secret_key_ai.get_secret_value(),
        )
        print(embeddings)
        res = await embeddings.embed_query(text="Привет")
        print(res)
        print(len(res))

    asyncio.run(main())
