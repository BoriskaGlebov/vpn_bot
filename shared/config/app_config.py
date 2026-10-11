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

    `app_config.toml` — обязательная базовая конфигурация, читается всегда.
    Поверх неё по очереди деплохо (глубоким объединением через `deep_merge`,
    каждый следующий имеет приоритет) накладываются, если присутствуют:
        - `app_config.develop.toml` — только если `STAGE != "prod"`;
        - `app_config.local.toml` — независимо от `STAGE`.

    Returns
        dict[str, Any]: Итоговый конфиг в виде словаря.

    Notes
        - `app_config.develop.toml`/`app_config.local.toml` опциональны и
          дополняют базовый конфиг, а не заменяют его — ключ, заданный
          только в `app_config.toml`, присутствует в итоге на любой стадии.
        - Файлы читаются в бинарном режиме (`rb`) для совместимости с `tomllib`.

    Raises
        FileNotFoundError: Если `app_config.toml` отсутствует.
        tomllib.TOMLDecodeError: Если один из файлов содержит невалидный TOML.

    """
    logger.info("Загружаю настройки для бота из временного окружения.")
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR / ".env.dev", override=True)
    load_dotenv(BASE_DIR / ".env.local", override=True)

    base_path = BASE_DIR / "app_config.toml"
    dev_path = BASE_DIR / "app_config.develop.toml"
    local_path = BASE_DIR / "app_config.local.toml"

    if not base_path.exists():
        raise FileNotFoundError(f"Базовый конфиг не найден: {base_path}")

    with base_path.open("rb") as f:
        config = tomllib.load(f)

    stage = os.getenv("STAGE", "prod")
    if stage != "prod" and dev_path.exists():
        with dev_path.open("rb") as f:
            config = deep_merge(config, tomllib.load(f))

    if local_path.exists():
        with local_path.open("rb") as f:
            config = deep_merge(config, tomllib.load(f))

    return config


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
     admin_ids (list[int]):
            Список Telegram ID администраторов с расширенными правами.
            Через переменную окружения задаётся JSON-массивом, например
            `ADMIN_IDS=[123456789, 987654321]` — pydantic-settings разбирает
            `list[int]` как JSON, а не как строку с разделителем-запятой.
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
    admin_ids: list[int] = []
