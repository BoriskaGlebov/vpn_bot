import time
from typing import Any

from core.config import settings_ai
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio


class YandexChatModel(BaseChatModel):
    """Чат-модель LangChain для работы с Yandex AI Studio.

    Класс реализует адаптер над SDK Yandex AI Studio и позволяет использовать
    модели Yandex через интерфейс `BaseChatModel` из LangChain.

    Attributes
       _sdk (AsyncAIStudio): Асинхронный клиент Yandex AI Studio.
       _model: Сконфигурированный объект модели чата.

    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Инициализирует клиент Yandex AI Studio и конфигурирует модель.

        Args:
            *args: Позиционные аргументы, передаваемые в `BaseChatModel`.
            **kwargs: Именованные аргументы, передаваемые в `BaseChatModel`.

        """
        super().__init__(*args, **kwargs)
        self._sdk = AsyncAIStudio(
            folder_id=settings_ai.yandex_folder_id,
            auth=settings_ai.secret_key_ai.get_secret_value(),
        )

        self._model = self._sdk.chat.completions(settings_ai.yandex_model).configure(
            temperature=0.3,
            max_tokens=512,
        )
        logger.info("YandexChatModel инициализирован успешно")

    @property
    def _llm_type(self) -> str:
        """Возвращает тип LLM.

        Используется LangChain для идентификации типа модели.

        Returns
           str: Строковый идентификатор модели.

        """
        return "yandex"

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Асинхронно генерирует ответ модели.

        Args:
            messages: Список сообщений диалога.
            stop: Список стоп-последовательностей.
            **kwargs: Дополнительные параметры генерации.

        Returns
            ChatResult: Результат генерации модели.

        """
        start_time = time.perf_counter()
        logger.debug(
            "Запрос к Yandex LLM | messages_count={} stop={}",
            len(messages),
            stop,
        )
        prompt = "\n".join(str(m.content) for m in messages)
        try:
            result = await self._model.run(prompt)
            latency = time.perf_counter() - start_time
            logger.debug(
                "Ответ от Yandex LLM получен | latency={:.3f}s response_length={}",
                latency,
                len(result.text),
            )

            message = AIMessage(content=result.text)
            generation = ChatGeneration(message=message)

            return ChatResult(generations=[generation])
        except Exception:
            logger.exception(
                "Ошибка при вызове Yandex LLM | messages_count={}",
                len(messages),
            )
            raise

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Синхронно генерирует ответ модели."""
        raise NotImplementedError("Sync generation not supported")
