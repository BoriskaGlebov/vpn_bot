from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SettingsApp(BaseSettings):
    """Базовая конфигурация приложения.

    Attributes
     stage (str): Стадия проекта develop, prod, local, в зависимости от места разработки.
     session_secret (SecretStr): Подпись сессии.
     debug_fast_api (bool): Включить режим отладки FastAPI.
     reload_fast_api (bool): Включить автоматическую перезагрузку FastAPI при изменениях кода.
     base_dir (Path): Корневая директория проекта, вычисляется автоматически.
     logger_level_stdout (str): Уровень логирования для стандартного вывода.
     logger_level_file (str): Уровень логирования для файла логов.
     logger_error_file (str): Уровень логирования для ошибок в отдельном файле.
     model_config (SettingsConfigDict): Настройки Pydantic для загрузки конфигурации из .env.
     api_url (str): Адрес api интеграции.
     api_port (int): Порт для api.

    """

    stage: str = "prod"
    session_secret: SecretStr = SecretStr("secret")
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    debug_fast_api: bool = False
    reload_fast_api: bool = False
    logger_level_stdout: str = "INFO"
    logger_level_file: str = "INFO"
    logger_error_file: str = "WARNING"

    api_url: str = "127.0.0.1"
    api_port: str = 8089

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),  # базовые значения
            str(BASE_DIR / ".env.local"),  # локальные переопределяют .env
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )
