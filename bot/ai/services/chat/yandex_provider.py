from loguru import logger
from yandex_ai_studio_sdk import AsyncAIStudio

from bot.ai.services.chat.base import BaseLLMProvider
from bot.config import settings_ai


class YandexLLMProvider(BaseLLMProvider):
    """Провайдер LLM для работы с Yandex AI Studio (асинхронный).

    Используется для генерации ответов Telegram-бота на основе
    переданного контекста. Генерация происходит строго на основе
    контекста, без добавления внешних знаний.
    """

    def __init__(self) -> None:
        """Инициализация провайдера.

        Создаёт объект SDK Yandex AI Studio и конфигурирует
        модель чат-комплешенов.

        """
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
        logger.info("YandexLLMProvider инициализирован успешно")

    async def generate(self, context: str, question: str) -> str:
        """Генерирует ответ на вопрос на основе переданного контекста.

        Args:
            context (str): Контекст, содержащий информацию из базы знаний.
            question (str): Вопрос пользователя.

        Returns
            str: Ответ модели на основе контекста.

        Raises
            ValueError: Если `context` или `question` пустые.
            Exception: Пробрасывает ошибки SDK Yandex AI Studio.

        """
        if not context.strip():
            raise ValueError("context не может быть пустым")
        if not question.strip():
            raise ValueError("question не может быть пустым")

        full_prompt = (
            f"{self._system_prompt}\n\nКонтекст:\n{context}\n\nВопрос:\n{question}"
        )

        logger.debug(
            "Генерация ответа: контекст {} символов, вопрос {} символов",
            len(context),
            len(question),
        )

        try:
            result = await self._model.run(full_prompt)
            answer = result.text.strip() if result.text else ""
            if not answer:
                logger.warning(
                    "Результат генерации пустой, возможно нет подходящего контекста"
                )
            else:
                logger.info("Ответ сгенерирован успешно ({} символов)", len(answer))
            return answer
        except Exception as e:
            logger.exception(
                "Ошибка при генерации ответа через Yandex AI Studio: {}", e
            )
            raise
