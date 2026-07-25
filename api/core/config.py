import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr

from shared.config.app_config import (
    SettingsApp,
    SettingsCommon,
    load_toml_config,
)
from shared.config.db_config import PostgresSettings
from shared.config.logger_config import LoggerConfig

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SettingsAPI(SettingsCommon):
    """Конфигурация API-сервиса.

    Расширяет базовые настройки приложения (`SettingsCommon`) параметрами,
    специфичными для FastAPI-сервиса, и агрегирует конфигурации
    других подсистем (ядро приложения и база данных).

    Attributes
        core (SettingsApp):
            Основные настройки приложения (бизнес-логика, бот, XRay, прокси и т.д.).

        db (PostgresSettings):
            Конфигурация подключения к PostgreSQL базе данных.
            Включает параметры подключения и формирование URL.



        session_secret (SecretStr):
            Секретный ключ для подписи сессий (например, cookies или JWT).

        internal_api_secret (SecretStr):
            Общий секрет, которым бот подписывает запросы к api/
            (заголовок X-Internal-Secret). Без него X-Telegram-Id
            не принимается во внимание — см. AuthMiddleware.

    """

    core: SettingsApp = Field(default_factory=SettingsApp)
    db: PostgresSettings = Field(default_factory=PostgresSettings)

    session_secret: SecretStr = SecretStr("secret")
    internal_api_secret: SecretStr = SecretStr("secret")


load_dotenv(BASE_DIR / ".env.local")
env_conf = {
    "db": {
        "user": os.getenv("DB_USER"),
        "database": os.getenv("DB_NAME"),
    },
    "redis": {},
}
toml_loader = load_toml_config()
settings_api = SettingsAPI(**toml_loader)  # type: ignore

LoggerConfig(
    log_dir=BASE_DIR / "api" / "logs",
    logger_level_stdout=settings_api.core.logger_level_stdout,
    logger_level_file=settings_api.core.logger_level_file,
    logger_error_file=settings_api.core.logger_error_file,
)
