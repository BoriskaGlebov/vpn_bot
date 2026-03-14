import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough
from loguru import logger

from bot.ai.infrastructure.context.context_builder import SimpleContextBuilder
from bot.ai.infrastructure.promts.promt_rag import rag_prompt
from bot.ai.infrastructure.retrievers.pgvector_retriever import PgVectorRetriever


class RAGChain:
    """Класс для построения RAG (Retrieval-Augmented Generation) цепочки.

    Цепочка выполняет следующие шаги:
        1. Получение релевантного контекста через retriever.
        2. Построение контекста через context_builder.
        3. Формирование запроса через RAG prompt.
        4. Генерация ответа через LLM.
        5. Парсинг ответа через StrOutputParser.

    Attributes
        _chain: Собранная runnable цепочка для аcинхронного вызова.

    """

    def __init__(
        self,
        llm: BaseChatModel,
        retriever: PgVectorRetriever,
        context_builder: SimpleContextBuilder,
    ) -> None:
        """Инициализация RAGChain.

        Args:
           llm (BaseChatModel): Ядро LLM модели для генерации ответа.
           retriever (PgVectorRetriever): Retriever для поиска релевантных документов.
           context_builder (SimpleContextBuilder): Контекстный билдер для сборки контекста из документов.

        """
        logger.info("Инициализация RAGChain")
        retriever_runnable = RunnableLambda(retriever.aretrieve)
        context_builder_runnable = RunnableLambda(context_builder.build)

        self._chain: Runnable[Any, str] = (
            {
                "context": retriever_runnable | context_builder_runnable,
                "question": RunnablePassthrough(),
            }
            | rag_prompt
            | llm
            | StrOutputParser()
        )
        logger.debug("RAGChain успешно инициализирован")

    async def run(self, question: str) -> str:
        """Асинхронный запуск RAG цепочки для заданного вопроса.

        Args:
            question (str): Вопрос пользователя.

        Returns
            str: Сгенерированный ответ LLM с учетом контекста.

        Raises
            Exception: Любые ошибки внутри retriever, context_builder или LLM пробрасываются наружу.

        """
        start_time = time.perf_counter()
        logger.info("Запуск RAGChain для вопроса: {}", question[:50])

        try:
            answer = await self._chain.ainvoke(question)
        except Exception as e:
            logger.exception("Ошибка при выполнении RAGChain: {}", e)
            raise
        finally:
            elapsed = time.perf_counter() - start_time
            logger.info("RAGChain завершен за {:.3f} секунд", elapsed)

        logger.debug(
            "Сгенерирован ответ: {}",
            answer[:100] + ("..." if len(answer) > 100 else ""),
        )

        return answer
