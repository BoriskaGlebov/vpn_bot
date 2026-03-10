import asyncio
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio

from bot.config import settings_ai


class YandexChatModel(BaseChatModel):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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
        return "yandex"

    async def _agenerate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = "\n".join(m.content for m in messages)

        result = await self._model.run(prompt)

        message = AIMessage(content=result.text)

        generation = ChatGeneration(message=message)

        return ChatResult(generations=[generation])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        pass


if __name__ == "__main__":

    async def main():
        llm = YandexChatModel()

        prompt = ChatPromptTemplate.from_template(
            "Ответь коротко на вопрос: {question}"
        )

        chain = prompt | llm

        result = await chain.ainvoke({"question": "Что такое VPN?"})

        print(result.content)

    asyncio.run(main())
