from pathlib import Path

from shared.config.app_config import SettingsApp
from shared.config.db_config import SettingsDB
from shared.config.logger_config import LoggerConfig

BASE_DIR = Path(__file__).resolve().parent.parent


# TODO убрать в дальнейшем закомментированный код


class SettingsAPI(SettingsApp):
    """Конфигурация API-сервиса.

    Расширяет базовые настройки приложения (`SettingsApp`) параметрами,
    специфичными для FastAPI-сервиса.

    Attributes
        debug_fast_api (bool): Включает режим отладки FastAPI.
            Влияет на вывод ошибок и поведение приложения.
        reload_fast_api (bool): Включает авто-перезагрузку сервера при изменении кода.
            Используется только в режиме разработки.

    """

    ...


settings_api = SettingsAPI()  # type: ignore
settings_db = SettingsDB()  # type: ignore

LoggerConfig(
    log_dir=Path(__file__).resolve().parent / "logs",
    logger_level_stdout=settings_api.logger_level_stdout,
    logger_level_file=settings_api.logger_level_file,
    logger_error_file=settings_api.logger_error_file,
)
