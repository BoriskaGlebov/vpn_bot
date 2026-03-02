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
            "Ты ассистент Telegram-бота VPN Boriska.\n\n"
            "Ты отвечаешь ТОЛЬКО на основе переданного контекста.\n"
            "Контекст содержит фрагменты базы знаний бота.\n\n"
            "Правила ответа:\n"
            "1. Сформулируй ответ своими словами.\n"
            "2. Не копируй предложения из контекста дословно.\n"
            "3. Если это инструкция — пересобери её в логичные шаги.\n"
            "4. Убери повторы и лишние детали.\n"
            "5. Сделай ответ кратким, структурированным и понятным.\n"
            "6. Используй 1–2 уместных эмодзи.\n\n"
            "Если в контексте нет информации для ответа — честно скажи, "
            "что информации недостаточно.\n"
            "Не добавляй знания от себя и не придумывай."
        )

    async def generate(self, context: str, question: str) -> str:
        full_prompt = (
            f"{self._system_prompt}\n\n"
            f"Контекст:\n{context}\n\n"
            f"Вопрос:\n{question}"
        )

        result = await self._model.run(full_prompt)
        return result.text
