from langchain_core.embeddings import Embeddings
from loguru import logger

from bot.ai.infrastructure.embeddings.local_embeddings import LocalEmbeddings
from bot.ai.infrastructure.embeddings.yandex_embeddings import YandexEmbeddings
from bot.config import settings_ai
from bot.redis_service import redis_embedding_cache


class EmbeddingsFactory:
    """Фабрика для выбора локального или YandexEmbeddings."""

    @staticmethod
    def create() -> Embeddings:
        """Создаёт сервис эмбеддингов в зависимости от окружения.

        Returns
            Embeddings: Реализация сервиса эмбеддингов.

        """
        if settings_ai.skip_ai_init:
            logger.info("Используем YandexEmbeddings для PROD")
            return YandexEmbeddings(
                folder_id=settings_ai.yandex_folder_id,
                api_key=settings_ai.secret_key_ai.get_secret_value(),
                normalize=settings_ai.normalize,
                cache=redis_embedding_cache,
            )
        logger.info("Используем локальный LocalEmbeddings для DEV")
        if settings_ai.model_llm_name is None:
            raise ValueError(
                "model_llm_name должно быть установлено для LocalEmbeddings"
            )
        return LocalEmbeddings(
            model_name=settings_ai.model_llm_name,
            normalize=settings_ai.normalize,
        )
