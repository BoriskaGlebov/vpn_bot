import asyncio

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from bot.ai.infrastructure.context.context_builder import SimpleContextBuilder
from bot.ai.infrastructure.embeddings.factory_embeddings import EmbeddingsFactory
from bot.ai.infrastructure.llm.yandex_llm import YandexChatModel
from bot.ai.infrastructure.promts.promt_rag import rag_prompt
from bot.ai.infrastructure.retrievers.pgvector_retriever import PgVectorRetriever
from bot.database import async_session


class RAGChain:

    def __init__(
        self, llm, retriever: PgVectorRetriever, context_builder: SimpleContextBuilder
    ) -> None:
        retriever_runnable = RunnableLambda(retriever.aretrieve)
        context_builder = RunnableLambda(context_builder.build)

        self._chain = (
            {
                "context": retriever_runnable | context_builder,
                "question": RunnablePassthrough(),
            }
            | rag_prompt
            | llm
            | StrOutputParser()
        )

    async def run(self, question: str):
        return await self._chain.ainvoke(question)


if __name__ == "__main__":

    async def main():
        emb = EmbeddingsFactory().create()

        retriever = PgVectorRetriever(embeddings=emb, session_factory=async_session)

        context_builder = SimpleContextBuilder()
        question = "Что такое твой VPN?"
        llm = YandexChatModel()
        rag_chain = RAGChain(llm, retriever, context_builder)
        answer = await rag_chain.run(question)
        print("\n===== ANSWER =====\n")
        print(answer)

    asyncio.run(main())
