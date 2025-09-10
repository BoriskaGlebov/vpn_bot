import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger
from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.dialogs.dialogs_text import dialogs

__all__ = [
    "logger",
]


class SettingsBot(BaseSettings):
    """Конфигурация бота и логирования.

    Attributes
        BOT_TOKEN (SecretStr): Токен бота, используемый для подключения к Telegram Bot API.
        ADMIN_IDS (List[int]): Список ID администраторов, имеющих доступ к расширенным функциям.
        BASE_SITE (str): Адрес куда webhook слать.
        USE_POLING (boo) : Использования полинга в тестах  False по умолчанию
        DEBUG_FAST_API (bool): Режим debug вкл или выкл.
        RELOAD_FAST_API (bool): Режим перезагрузки сервера при внесении изменений вкл или выкл.
        BASE_DIR (Path): Базовая директория проекта, вычисляется относительно текущего файла.
        LOGGER_LEVEL_STDOUT (str): Уровень логирования для вывода в стандартный поток.
        LOGGER_LEVEL_FILE (str): Уровень логирования для вывода в файл.
        LOGGER_ERROR_FILE (str): Уровень логирования для ошибок, сохраняемых в отдельный файл.
        MESSAGES (dict): Конфиг файл с диалогами бота.
        model_config (SettingsConfigDict): Конфигурация pydantic settings
            (путь до .env, кодировка и поведение при лишних переменных).
    Properties
        WEBHOOK_URL (str): URL вебхука. Формируется автоматически на основе BASE_SITE.

    """

    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    BASE_SITE: str
    USE_POLING: bool = False
    DEBUG_FAST_API: bool = True
    RELOAD_FAST_API: bool = True

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    LOGGER_LEVEL_STDOUT: str = "DEBUG"
    LOGGER_LEVEL_FILE: str = "DEBUG"
    LOGGER_ERROR_FILE: str = "WARNING"

    MESSAGES: Dict[str, Any] = dialogs

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    def WEBHOOK_URL(self) -> str:
        """Возвращает URL вебхука."""
        return f"{self.BASE_SITE}/webhook"


class SettingsDB(BaseSettings):
    """Конфигурация базы данных и Redis для проекта.

    Attributes
        DB_HOST (str): Хост PostgreSQL-сервера. По умолчанию "localhost".
        DB_PORT (int): Порт PostgreSQL-сервера. По умолчанию 5432.
        DB_USER (str): Имя пользователя для подключения к базе данных.
        DB_PASSWORD (SecretStr): Пароль пользователя для подключения к базе данных.
        DB_DATABASE (str): Имя базы данных.
        REDIS_PASSWORD (SecretStr): Пароль для подключения к Redis.
        REDIS_HOST (str): Хост Redis-сервера. По умолчанию "localhost".
        REDIS_PORT (int): Порт Redis-сервера. По умолчанию 6379.
        NUM_DB (int): Номер базы данных Redis. По умолчанию 0.

    Properties
        DATABASE_URL (str): Строка подключения к PostgreSQL в формате
            `postgresql+asyncpg://user:password@host:port/database`.
            Формируется автоматически из указанных выше атрибутов.
        REDIS_URL (str): Строка подключения к Redis в формате
            `redis://:password@host:port/db_number`.
    Configuration
        model_config (SettingsConfigDict): Конфигурация pydantic settings
            (путь до .env, кодировка и поведение при лишних переменных).

    """

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_DATABASE: str

    REDIS_PASSWORD: SecretStr
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    NUM_DB: int = 0

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    def DATABASE_URL(self) -> str:
        """Строка подключения к PostgreSQL через asyncpg.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD.get_secret_value()}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_DATABASE}"
        )

    @computed_field
    def REDIS_URL(self) -> str:
        """Строка подключения к Redis.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"redis://:{self.REDIS_PASSWORD.get_secret_value()}@"
            f"{self.REDIS_HOST}:{self.REDIS_PORT}/{self.NUM_DB}"
        )


class LoggerConfig:
    """Настройка логирования с использованием loguru.

    Args:
        log_dir (Path): Путь к директории для хранения логов.
        logger_level_stdout (str, optional): Уровень логирования для вывода в stdout. Defaults to "INFO".
        logger_level_file (str, optional): Уровень логирования для основного файла лога. Defaults to "DEBUG".
        logger_error_file (str, optional): Уровень логирования для файла ошибок. Defaults to "ERROR".
        extra_defaults (Optional[Dict[str, Any]], optional): Значения по умолчанию для extra полей. Defaults to None.

    """

    def __init__(
        self,
        log_dir: Path,
        logger_level_stdout: str = "INFO",
        logger_level_file: str = "DEBUG",
        logger_error_file: str = "WARNING",
        extra_defaults: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.log_dir = log_dir
        self.logger_level_stdout = logger_level_stdout
        self.logger_level_file = logger_level_file
        self.logger_error_file = logger_error_file
        self.extra_defaults = extra_defaults or {"user": "-"}

        self._ensure_log_dir_exists()
        self._setup_logging()

    def _ensure_log_dir_exists(self) -> None:
        """Создает директорию для логов, если она не существует, и устанавливает права доступа."""
        if not self.log_dir.exists():
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

    @staticmethod
    def _user_filter(record: Mapping[str, Any]) -> bool:
        """Фильтр для логов с указанным пользователем.

        Args:
            record (Mapping[str, Any]): Запись лога.

        Returns
            bool: True, если поле 'user' в extra присутствует и не равно "-".

        """
        user = record.get("extra", {}).get("user")
        return bool(user and user != "-")

    @staticmethod
    def _default_filter(record: Mapping[str, Any]) -> bool:
        """Фильтр для логов без данных пользователя.

        Args:
            record (Mapping[str, Any]): Запись лога.

        Returns
            bool: True, если поле 'user' отсутствует или равно "-".

        """
        user = record.get("extra", {}).get("user")
        return user in (None, "-")

    @staticmethod
    def _exclude_errors(record: Mapping[str, Any]) -> bool:
        """Исключает записи с уровнем WARNING.

        Создаются два файла для обычных логов и для ошибок,
        так вот warning идет в блок ошибок.

        Args:
            record (Mapping[str, Any]): Запись лога.

        Returns
            bool: True, если уровень лога ниже WARNING.

        """
        return int(record["level"].no) < int(logger.level("WARNING").no)

    def _filter_for_files(self, record: Mapping[str, Any]) -> bool:
        """Объединенный фильтр для файловых логов.

        Args:
            record (Mapping[str, Any]): Запись лога.

        Returns
            bool: True, если запись подходит по фильтру пользователя и не является ошибкой.

        """
        return (
            self._user_filter(record) or self._default_filter(record)
        ) and self._exclude_errors(record)

    def _setup_logging(self) -> None:
        """Конфигурирует логирование, удаляя все текущие обработчики и добавляя новые."""
        logger.remove()
        logger.configure(extra=self.extra_defaults)
        self._add_stdout_handler()
        self._add_file_handlers()

    def _add_stdout_handler(self) -> None:
        """Добавляет обработчик для вывода логов в stdout."""
        logger.add(
            sys.stdout,
            level=self.logger_level_stdout,
            format=self._get_format(),
            filter=lambda r: self._user_filter(r) or self._default_filter(r),
            catch=True,
            diagnose=True,
            enqueue=True,
        )

    def _add_file_handlers(self) -> None:
        """Добавляет обработчики для записи логов в файлы."""
        log_file_path = self.log_dir / "file.log"
        error_log_file_path = self.log_dir / "error.log"

        logger.add(
            str(log_file_path),
            level=self.logger_level_file,
            format=self._get_format(),
            rotation="1 day",
            retention="30 days",
            catch=True,
            backtrace=True,
            diagnose=True,
            filter=self._filter_for_files,
            enqueue=True,
        )

        logger.add(
            str(error_log_file_path),
            level=self.logger_error_file,
            format=self._get_format(),
            rotation="1 day",
            retention="30 days",
            catch=True,
            backtrace=True,
            diagnose=True,
            filter=lambda r: self._user_filter(r) or self._default_filter(r),
            enqueue=True,
        )

    @staticmethod
    def _get_format() -> str:
        """Возвращает формат строки для логов.

        Returns
            str: Формат строки для loguru.

        """
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - "
            "<level>{level:^10}</level> - "
            "<cyan>{name}</cyan>:<magenta>{line}</magenta> - "
            "<yellow>{function}</yellow> - "
            "<magenta>{extra[user]:^15}</magenta> - "
            "<white>{message}</white>"
        )


settings_bot = SettingsBot()
settings_db = SettingsDB()

LoggerConfig(
    log_dir=Path(__file__).resolve().parent / "logs",
    logger_level_stdout=settings_bot.LOGGER_LEVEL_STDOUT,
    logger_level_file=settings_bot.LOGGER_LEVEL_FILE,
    logger_error_file=settings_bot.LOGGER_ERROR_FILE,
)
# Инициализируем бота и диспетчер
bot: Bot = Bot(
    token=settings_bot.BOT_TOKEN.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
# Хранилище FSM
storage = RedisStorage.from_url(str(settings_db.REDIS_URL))
# Это если работать без Redis
# dp = Dispatcher(storage=MemoryStorage())
# Это если работать через Redis
dp = Dispatcher(storage=storage)

if __name__ == "__main__":
    # logger.bind(user="Boris").debug("Сообщение")
    # logger.bind(filename="Boris_file.txt").debug("Сообщение")
    # logger.bind(user="Boris", filename="Boris_file.txt").warning("Сообщение")
    # logger.debug("Сообщение")
    # logger.error("wasd")
    # logger.bind(user="Boris").warning("Сообщение")
    # logger.bind(filename="Boris_file.txt").error("Сообщение")
    print(settings_bot.WEBHOOK_URL)
    print(settings_db.model_dump())
    # print(settings_db.model_dump_json())
