from abc import ABC

from langchain_core.documents import Document
from loguru import logger


class ContextBuilder(ABC):
    """Абстрактный базовый класс для сборки контекста из документов."""

    async def build(self, docs: list[Document]) -> str:
        """Сборка контекста из документов.

        Args:
            docs (List[Document]): Список документов для включения в контекст.

        Returns
            str: Собранный текстовый контекст.

        Raises
            NotImplementedError: Если метод не переопределён в наследнике.

        """
        raise NotImplementedError


class SimpleContextBuilder(ContextBuilder):
    """Простая реализация ContextBuilder с ограничением по количеству символов.

    Собирает текст из документов по порядку до достижения максимального
    числа символов.

    Attributes
        max_chars (int): Максимальное количество символов в итоговом контексте.

    """

    def __init__(self, max_chars: int = 3000) -> None:
        """Инициализация SimpleContextBuilder.

        Args:
           max_chars (int, optional): Максимальное число символов в контексте.
               По умолчанию 3000.

        """
        self.max_chars = max_chars

    async def build(self, docs: list[Document]) -> str:
        """Асинхронная сборка контекста из списка документов.

        Итеративно добавляет текст каждого документа в итоговый контекст.
        Если добавление нового документа превысит `max_chars`, сборка останавливается.

        Args:
            docs (List[Document]): Список документов для включения в контекст.

        Returns
            str: Итоговый текстовый контекст с документами,
                каждый документ начинается с идентификатора `[chunk id]`.

        """
        context_parts = []
        total_chars: int = 0
        added_docs: int = 0

        for doc in docs:
            chunk_id = doc.metadata.get("chunk_id")
            text = f"[chunk {chunk_id}]\n{doc.page_content}"

            if total_chars + len(text) > self.max_chars:
                logger.debug(
                    "Превышено max_chars=%d, остановка сборки контекста", self.max_chars
                )
                break

            context_parts.append(text)
            total_chars += len(text)
            added_docs += 1

        logger.debug(
            "Собрано контекста: %d документов, %d символов",
            added_docs,
            total_chars,
        )

        return "\n\n".join(context_parts)
