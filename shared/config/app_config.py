import os
import tomllib
from pathlib import Path
from pprint import pprint
from typing import Any
from zoneinfo import ZoneInfo

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
    """Загружает конфигурацию из TOML-файла текущей стадии (`STAGE`).

    `prod` и `develop` — разные физические окружения (разные сервера, разные
    учётные данные, разные VPN-ноды), поэтому их конфиги не объединяются
    между собой: `STAGE` выбирает РОВНО ОДИН файл как полный,
    самодостаточный конфиг этого окружения:
        - `STAGE=prod` (по умолчанию) — `app_config.toml`;
        - любой другой `STAGE` (`develop`, `local` и т.д.) — `app_config.develop.toml`.
    Настройка, добавленная только в `app_config.toml`, на develop не
    появляется сама по себе — её нужно продублировать в
    `app_config.develop.toml`, если она там тоже нужна.

    Поверх выбранного файла, независимо от стадии, накладывается
    (глубоким объединением через `deep_merge`) `app_config.local.toml`, если
    он существует — это личные оверрайды разработчика для любого окружения.

    Returns
        dict[str, Any]: Итоговый конфиг в виде словаря.

    Notes
        - `app_config.local.toml` опционален и дополняет выбранный стадией
          файл, а не заменяет его.
        - Файлы читаются в бинарном режиме (`rb`) для совместимости с `tomllib`.

    Raises
        FileNotFoundError: Если файл, выбранный текущей стадией, отсутствует.
        tomllib.TOMLDecodeError: Если один из файлов содержит невалидный TOML.

    """
    logger.info("Загружаю настройки для бота из временного окружения.")
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR / ".env.dev", override=True)
    load_dotenv(BASE_DIR / ".env.local", override=True)

    base_path = BASE_DIR / "app_config.toml"
    dev_path = BASE_DIR / "app_config.develop.toml"
    local_path = BASE_DIR / "app_config.local.toml"

    stage = os.getenv("STAGE", "prod")
    stage_path = base_path if stage == "prod" else dev_path

    if not stage_path.exists():
        raise FileNotFoundError(f"Конфиг для STAGE={stage!r} не найден: {stage_path}")

    with stage_path.open("rb") as f:
        config = tomllib.load(f)

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
     logger_diagnose_files (bool): Отладочный флаг логгера, пишет подробнее логи включая секреты
     max_configs_per_user (int): Максимальное количество файлов конфига для одного пользователя
     common_timeout (int): Настройка таймаута при подключении к API, серверам, контейнерам.
     admin_ids (list[int]):
            Список Telegram ID администраторов с расширенными правами.
            Через переменную окружения задаётся JSON-массивом, например
            `ADMIN_IDS=[123456789, 987654321]` — pydantic-settings разбирает
            `list[int]` как JSON, а не как строку с разделителем-запятой.
     timezone (str):
            IANA-имя таймзоны проекта (например, `Europe/Moscow`). Единая
            точка настройки для всех `datetime.now(...)` в `bot/` и `api/` —
            раньше таймзона была захардкожена как `UTC` в коде, а контейнеры
            при этом работают в `Europe/Moscow` (`TZ` в
            `docker-compose.common.yml`); naive-вызовы `datetime.now()`
            читали OS-таймзону (Moscow), а explicit-вызовы `datetime.now(UTC)`
            — настоящий UTC, и эти значения расходились при сравнении/записи
            в одну и ту же колонку (см. #255). Единый источник настройки
            убирает расхождение и позволяет сменить зону без правки кода.
     model_config (SettingsConfigDict): Настройки Pydantic для загрузки конфигурации из .env.

    """

    stage: str = "prod"
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    debug_fast_api: bool = False
    reload_fast_api: bool = False
    logger_level_stdout: str = "INFO"
    logger_level_file: str = "INFO"
    logger_error_file: str = "WARNING"
    logger_diagnose_files: bool = False
    max_configs_per_user: int = 10
    common_timeout: int = 10
    admin_ids: list[int] = []
    timezone: str = "Europe/Moscow"

    @property
    def tzinfo(self) -> ZoneInfo:
        """`ZoneInfo`, построенная из `timezone` — использовать вместо `datetime.UTC`.

        Returns
            ZoneInfo: таймзона проекта, применяется ко всем
                `datetime.now(...)` в `bot/` и `api/`.

        """
        return ZoneInfo(self.timezone)


if __name__ == "__main__":
    toml = load_toml_config()
    settings = SettingsApp(**toml)
    pprint(settings.model_dump())
