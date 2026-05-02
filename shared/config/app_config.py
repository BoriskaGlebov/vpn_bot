from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SettingsCommon(BaseSettings):
    """Базовый класс с настройками, показывает, где брать переменные."""

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),  # базовые значения
            str(BASE_DIR / ".env.dev"),  # локальные переопределяют .env
            str(BASE_DIR / ".env.local"),  # локальные переопределяют .env
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


class SettingsApp(SettingsCommon):
    """Базовая конфигурация приложения.

    Attributes
     stage (str): Стадия проекта develop, prod, local, в зависимости от места разработки.

     debug_fast_api (bool): Включить режим отладки FastAPI.
     reload_fast_api (bool): Включить автоматическую перезагрузку FastAPI при изменениях кода.
     base_dir (Path): Корневая директория проекта, вычисляется автоматически.
     logger_level_stdout (str): Уровень логирования для стандартного вывода.
     logger_level_file (str): Уровень логирования для файла логов.
     logger_error_file (str): Уровень логирования для ошибок в отдельном файле.
     max_configs_per_user (int): Максимальное количество файлов конфига для одного пользователя
     common_timeout (int): Настройка таймаута при подключении к API, серверам, контейнерам.
     model_config (SettingsConfigDict): Настройки Pydantic для загрузки конфигурации из .env.

    """

    stage: str = "prod"
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    debug_fast_api: bool = False
    reload_fast_api: bool = False
    logger_level_stdout: str = "INFO"
    logger_level_file: str = "INFO"
    logger_error_file: str = "WARNING"
    max_configs_per_user: int = 10
    common_timeout: int = 10
