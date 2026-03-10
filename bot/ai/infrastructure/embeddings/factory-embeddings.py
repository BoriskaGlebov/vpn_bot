from ai.infrastructure.embeddings.local_embeddings import LocalEmbeddings
from ai.infrastructure.embeddings.yandex_embeddings import YandexEmbeddings
from config import settings_ai


class EmbeddingsFactory:

    @staticmethod
    def create():
        if settings_ai.skip_ai_init:
            return YandexEmbeddings(
                folder_id=settings_ai.yandex_folder_id,
                api_key=settings_ai.secret_key_ai.get_secret_value(),
                normalize=settings_ai.normalize,
            )

        return LocalEmbeddings(
            model_name=settings_ai.model_llm_name,
            normalize=settings_ai.normalize,
        )
