from typing import Protocol


class BaseLLMProvider(Protocol):
    """Протокол для провайдеров LLM (Large Language Model).

    Классы, реализующие этот протокол, должны предоставлять
    асинхронный метод `generate`, который принимает контекст
    и вопрос, и возвращает сгенерированный текстовый ответ.
    """

    async def generate(self, context: str, question: str) -> str:
        """Генерирует ответ на вопрос на основе предоставленного контекста.

        Args:
            context (str): Текстовый контекст, в котором ищется ответ.
            question (str): Вопрос, на который нужно сгенерировать ответ.

        Returns
            str: Сгенерированный текстовый ответ.

        """
        ...
