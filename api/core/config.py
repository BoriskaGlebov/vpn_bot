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
            Обязателен — без значения по умолчанию: это единственная защита
            сессий SQLAdmin, отсутствие переменной должно останавливать
            запуск, а не подменяться константой (см. #247).

        internal_api_secret (SecretStr):
            Общий секрет, которым бот подписывает запросы к api/
            (заголовок X-Internal-Secret). Без него X-Telegram-Id
            не принимается во внимание — см. AuthMiddleware. Обязателен —
            без значения по умолчанию по той же причине, что и выше: это
            единственная проверка доступа к api/ (см. #247).

        admin_panel_user (str):
            Логин админ-панели SQLAdmin — отдельный от учётных данных БД.

        admin_panel_password_hash (SecretStr):
            Хеш пароля админ-панели (формат `pbkdf2_sha256.<iterations>.<salt>.<hash>`,
            см. `api.users.auth_admin.hash_password`). Разделитель — "." а не "$":
            значение проходит через GitHub Secret -> bash heredoc в деплое ->
            Docker Compose env_file, а Compose интерполирует "$VAR" внутри
            env_file-значений, из-за чего "$"-разделитель молча обрезал хеш в
            продакшене. Пустое значение по умолчанию —
            вход в панель отключён, пока хеш не задан явно.

    """

    core: SettingsApp = Field(default_factory=SettingsApp)
    db: PostgresSettings = Field(default_factory=PostgresSettings)

    session_secret: SecretStr
    internal_api_secret: SecretStr

    admin_panel_user: str = "admin"
    admin_panel_password_hash: SecretStr = SecretStr("")


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
    diagnose_files=settings_api.core.logger_diagnose_files,
)
