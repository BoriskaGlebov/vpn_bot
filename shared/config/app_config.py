import os
import tomllib
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивно объединяет два словаря.

    Значения из `b` имеют приоритет и переопределяют значения из `a`.
    Если значение по одному и тому же ключу в обоих словарях является словарём,
    выполняется рекурсивное объединение.

    Args:
        a (dict[str, Any]): Базовый словарь.
        b (dict[str, Any]): Словарь-переопределение.

    Returns
        dict[str, Any]: Новый словарь с результатом объединения.

    Notes
        - Функция не модифицирует входные словари (используется поверхностная копия `a`).
        - Если типы значений по одному ключу различаются (например, dict и list),
          значение из `b` полностью заменяет значение из `a`.
        - Объединение выполняется только для вложенных словарей.

    """
    result = a.copy()

    for k, v in b.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v

    return result


def load_toml_config() -> dict[str, Any]:
    """Загружает и объединяет конфигурацию из TOML-файлов.

    Читает два файла:
        - app_config.toml — базовая конфигурация
        - app_config.local.toml — локальные переопределения

    Если оба файла существуют, выполняется глубокое объединение через `deep_merge`,
    где значения из локального файла имеют приоритет.

    Returns
        dict[str, Any]: Итоговый конфиг в виде словаря.

    Notes
        - Оба файла опциональны.
        - Если существует только один файл — возвращается его содержимое.
        - Если ни один файл не найден — возвращается пустой словарь.
        - Файлы читаются в бинарном режиме (`rb`) для совместимости с `tomllib`.

    Raises
        tomllib.TOMLDecodeError: Если один из файлов содержит невалидный TOML.

    """
    logger.info("Загружаю настройки для бота из временного окружения.")
    base = {}
    local = {}
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR / ".env.dev", override=True)
    load_dotenv(BASE_DIR / ".env.local", override=True)

    base_path = BASE_DIR / "app_config.toml"
    dev_path = BASE_DIR / "app_config.develop.toml"
    local_path = BASE_DIR / "app_config.local.toml"
    dev_stage = os.getenv("STAGE", "prod")
    if dev_stage == "prod":
        base = tomllib.load(open(base_path, "rb"))
    else:
        base = tomllib.load(open(dev_path, "rb"))
    if local_path.exists():
        local = tomllib.load(open(local_path, "rb"))
    res_merge = deep_merge(base, local)
    return res_merge


class SettingsCommon(BaseSettings):
    """Базовый класс с настройками, показывает, где брать переменные."""

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env.test"),  # локальные переопределяют .env
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
    admin_ids: list[int] = []
