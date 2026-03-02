import asyncio
from pprint import pprint

from yandex_ai_studio_sdk import AsyncAIStudio

from bot.ai.services.chat.base import BaseLLMProvider
from bot.config import settings_ai


class YandexLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self._sdk = AsyncAIStudio(
            folder_id=settings_ai.yandex_folder_id,
            auth=settings_ai.secret_key_ai.get_secret_value(),
        )

        self._model = self._sdk.chat.completions(settings_ai.yandex_model).configure(
            temperature=0.3,
            max_tokens=512,
        )

        self._system_prompt = (
            "Ты полезный ассистент VPN бота.\n"
            "Та знаещь все про VPN и его технологии"
            "Отвечай кратко и по делу.\n"
            "Если информации нет — честно скажи."
            "Ответы давай со смайликами что б пользователю было приятно."
        )

    async def generate(self, prompt: str) -> str:
        full_prompt = f"{self._system_prompt}\n\nВопрос:\n{prompt}"

        result = await self._model.run(full_prompt)

        return result.text


if __name__ == "__main__":

    async def main():
        llm = YandexLLMProvider()
        res = await llm.generate(prompt="Земля круглая?")
        pprint(res)

    asyncio.run(main())
