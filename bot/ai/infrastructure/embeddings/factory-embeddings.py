from ai.infrastructure.embeddings.local_embeddings import LocalEmbeddings
from ai.infrastructure.embeddings.yandex_embeddings import YandexEmbeddings
from config import settings_ai
from loguru import logger


class EmbeddingsFactory:
    """Фабрика для выбора локального или YandexEmbeddings."""

    @staticmethod
    def create() -> YandexEmbeddings | LocalEmbeddings:
        """Возвращает сервис генерации эмбеддингов в зависимости от окружения."""
        if settings_ai.skip_ai_init:
            logger.info("Используем YandexEmbeddingService для PROD")
            return YandexEmbeddings(
                folder_id=settings_ai.yandex_folder_id,
                api_key=settings_ai.secret_key_ai.get_secret_value(),
                normalize=settings_ai.normalize,
            )
        logger.info("Используем локальный EmbeddingService для DEV")
        return LocalEmbeddings(
            model_name=settings_ai.model_llm_name,
            normalize=settings_ai.normalize,
        )
