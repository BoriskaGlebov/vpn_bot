from functools import cached_property
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class SettingsAI(BaseSettings):
    """Настройки конфигурации для интеграции с AI-сервисом.

    Класс загружает параметры из переменных окружения и файлов `.env`.
    Используется для хранения ключей доступа, параметров модели и
    дополнительных настроек обработки.

    Attributes
        secret_key_ai (SecretStr):
            Секретный ключ для безопасной аутентификации.

        yandex_folder_id (str):
            Идентификатор каталога в Yandex Cloud.

        yandex_model (str):
            Название используемой модели Yandex GPT.
            По умолчанию "yandexgpt-lite".

        common_chunks (list[dict[str, str]]):
            Список базовых сообщений (контекстных чанков),
            передаваемых в модель по умолчанию.

        model_llm_name (str|None ):
            Имя основной LLM-модели, используемой в приложении если локально делаю.

        normalize (bool):
            Флаг нормализации входных данных перед отправкой в модель.
            По умолчанию True.

    """

    secret_key_ai: SecretStr
    yandex_folder_id: str
    yandex_model: str = "yandexgpt-lite"
    model_llm_name: str | None
    normalize: bool = True
    skip_ai_init: bool = True

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),
            str(BASE_DIR / ".env.local"),
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TODO их бы надо вынести из сервиса бота они там не нужны.
    @cached_property
    def common_chunks(self) -> list[dict[str, str]]:
        """Чанки для работы ai сервиса."""
        from bot.dialogs.dialogs_text import chunks

        return chunks


if __name__ == "__main__":
    print(BASE_DIR)
