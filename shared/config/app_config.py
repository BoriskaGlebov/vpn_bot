import tomllib
from pathlib import Path
from typing import Any, Iterable

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def deep_merge(a: dict, b: dict) -> dict:
    result = a.copy()

    for k, v in b.items():
        if (
            k in result
            and isinstance(result[k], dict)
            and isinstance(v, dict)
        ):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v

    return result
def load_toml_config() -> dict[str, Any]:
    base = {}
    local = {}

    base_path = BASE_DIR /"app_config.toml"
    local_path = BASE_DIR / "app_config.local.toml"

    if base_path.exists():
        base = tomllib.load(open(base_path, "rb"))
    if local_path.exists():
        local = tomllib.load(open(local_path, "rb"))
    res_merge=deep_merge(base, local)
    return res_merge

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
     admin_ids (set[int] | str):
            Список Telegram ID администраторов с расширенными правами.
            Может задаваться строкой вида "1,2,3" или коллекцией чисел.
     model_config (SettingsConfigDict): Настройки Pydantic для загрузки конфигурации из .env.

     Methods
        parse_admin_ids(v):
            Валидирует и преобразует входное значение admin_ids в set[int].
            Поддерживает строку и iterable.

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
    admin_ids: list[int]=[]

    # @field_validator("admin_ids", mode="before")
    # @classmethod
    # def parse_admin_ids(cls, v: Any) -> set[int]:
    #     """Парсит строку с ID администраторов в множество целых чисел."""
    #     if isinstance(v, str):
    #         return set(int(i) for i in v.split(",") if i.strip().isdigit())
    #     if isinstance(v, Iterable):
    #         try:
    #             return {int(i) for i in v}
    #         except (ValueError, TypeError):
    #             raise ValueError("admin_ids должна содержать только целые числа")
    #
    #     raise TypeError("admin_ids должно быть строкой или коллекцией")


if __name__ == '__main__':
    res=load_toml_config()
    print(res )