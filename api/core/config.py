from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator

from shared.config.app_config import SettingsApp, SettingsCommon
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

            admin_ids (set[int] | str):
                Список Telegram ID администраторов с расширенными правами.
                Может задаваться строкой вида "1,2,3" или коллекцией чисел.

            session_secret (SecretStr):
                Секретный ключ для подписи сессий (например, cookies или JWT).

        Methods
            parse_admin_ids(v):
                Валидирует и преобразует входное значение admin_ids в set[int].
                Поддерживает строку и iterable.

        """

    core: SettingsApp = Field(default_factory=SettingsApp)
    db: PostgresSettings = Field(default_factory=PostgresSettings)

    admin_ids: set[int] | str = ""
    session_secret: SecretStr = SecretStr("secret")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> set[int]:
        """Парсит строку с ID администраторов в множество целых чисел."""
        if isinstance(v, str):
            return set(int(i) for i in v.split(",") if i.strip().isdigit())
        if isinstance(v, Iterable):
            try:
                return {int(i) for i in v}
            except (ValueError, TypeError):
                raise ValueError("admin_ids должна содержать только целые числа")

        raise TypeError("admin_ids должно быть строкой или коллекцией")


settings_api = SettingsAPI()  # type: ignore


LoggerConfig(
    log_dir=BASE_DIR / "api" / "logs",
    logger_level_stdout=settings_api.core.logger_level_stdout,
    logger_level_file=settings_api.core.logger_level_file,
    logger_error_file=settings_api.core.logger_error_file,
)
