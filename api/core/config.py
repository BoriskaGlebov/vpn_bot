from collections.abc import Iterable
from pathlib import Path
from pprint import pprint
from typing import Any

from pydantic import Field, SecretStr, field_validator

from shared.config.app_config import SettingsApp, SettingsCommon, load_toml_config
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



    """

    core: SettingsApp = Field(default_factory=SettingsApp)
    db: PostgresSettings = Field(default_factory=PostgresSettings)


    session_secret: SecretStr = SecretStr("secret")



toml_loader=load_toml_config()
settings_api = SettingsAPI(**toml_loader)  # type: ignore


LoggerConfig(
    log_dir=BASE_DIR / "api" / "logs",
    logger_level_stdout=settings_api.core.logger_level_stdout,
    logger_level_file=settings_api.core.logger_level_file,
    logger_error_file=settings_api.core.logger_error_file,
)
if __name__ == '__main__':
    print(load_toml_config())
    pprint(settings_api.core.model_dump())

