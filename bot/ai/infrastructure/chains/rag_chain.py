import asyncio

from ai.infrastructure.context.context_builder import SimpleContextBuilder
from ai.infrastructure.embeddings.factory_embeddings import EmbeddingsFactory
from ai.infrastructure.llm.yandex_llm import YandexChatModel
from ai.infrastructure.retrievers.pgvector_retriever import PgVectorRetriever
from database import async_session
from langchain_core.output_parsers import StrOutputParser
from transformers import RagRetriever
from transformers.models.distilbert.modeling_distilbert import Embeddings

from bot.ai.infrastructure.promts.promt_rag import rag_prompt


class RAGChain:

    def __init__(self, llm):
        self._chain = rag_prompt | llm | StrOutputParser()

    async def run(self, question: str, context: str):
        return await self._chain.ainvoke(
            {
                "question": question,
                "context": context,
            }
        )


if __name__ == "__main__":

    async def main():
        async with async_session() as session:
            question = "Как подключить VPN?"
            llm = YandexChatModel()
            emb = EmbeddingsFactory().create()
            retriever = PgVectorRetriever(embeddings=emb)
            documents = await retriever.aretrieve(question, session)
            print(documents)
            context_builder = SimpleContextBuilder()
            context = await context_builder.build(documents)
            print("\n===== CONTEXT =====\n")
            print(context)
            rag_chain = RAGChain(llm)
            answer = await rag_chain.run(question, context)
            print("\n===== ANSWER =====\n")
            print(answer)

    asyncio.run(main())
