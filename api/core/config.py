from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import field_validator

from shared.config.app_config import SettingsApp
from shared.config.db_config import SettingsDB
from shared.config.logger_config import LoggerConfig

BASE_DIR = Path(__file__).resolve().parent.parent


class SettingsAPI(SettingsApp):
    """Конфигурация API-сервиса.

    Расширяет базовые настройки приложения (`SettingsApp`) параметрами,
    специфичными для FastAPI-сервиса.

    Attributes
        admin_ids (Union[Set[int], str]): Список Telegram ID администраторов с расширенными правами.

    """

    admin_ids: set[int] | str = ""

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
settings_db = SettingsDB()  # type: ignore

LoggerConfig(
    log_dir=Path(__file__).resolve().parent / "logs",
    logger_level_stdout=settings_api.logger_level_stdout,
    logger_level_file=settings_api.logger_level_file,
    logger_error_file=settings_api.logger_error_file,
)
