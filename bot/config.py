import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger
from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.dialogs.dialogs_text import dialogs

__all__ = ["logger", "settings_bot", "settings_db", "bot", "dp"]
BASE_DIR = Path(__file__).resolve().parent.parent


class SettingsBot(BaseSettings):
    """Конфигурация бота и логирования.

    Attributes
        bot_token (SecretStr): Токен бота для подключения к Telegram Bot API.
        admin_ids (Union[Set[int], str]): Список Telegram ID администраторов с расширенными правами.
        base_site (str): Базовый URL сайта, используемый для формирования вебхука.
        vpn_host (str): Хост VPN-сервера.
        vpn_username (str): Имя пользователя для подключения к VPN.
        vpn_container (str): Имя Docker-контейнера VPN (если используется).
        max_configs_per_user (int): Максимальное количество файлов конфига для одного пользователя
        use_polling (bool): Использовать polling вместо webhook (по умолчанию False, удобно для тестов).
        debug_fast_api (bool): Включить режим отладки FastAPI.
        reload_fast_api (bool): Включить автоматическую перезагрузку FastAPI при изменениях кода.
        base_dir (Path): Корневая директория проекта, вычисляется автоматически.
        logger_level_stdout (str): Уровень логирования для стандартного вывода.
        logger_level_file (str): Уровень логирования для файла логов.
        logger_error_file (str): Уровень логирования для ошибок в отдельном файле.
        messages (dict[str, Any]): Словарь с текстами сообщений бота (диалоги, подсказки и т.д.).
        price_map (dict[int, int]): Карта цен подписок по месяцам, может быть задана через .env в JSON.
        model_config (SettingsConfigDict): Настройки Pydantic для загрузки конфигурации из .env.
    Properties
        webhook_url (str): URL вебхука. Формируется автоматически на основе BASE_SITE.

    """

    bot_token: SecretStr
    admin_ids: set[int] | str = ""
    base_site: str

    vpn_host: str
    vpn_username: str
    vpn_container: str
    max_configs_per_user: int = 10

    use_polling: bool = False
    debug_fast_api: bool = False
    reload_fast_api: bool = False

    base_dir: Path = Path(__file__).resolve().parent.parent

    logger_level_stdout: str = "INFO"
    logger_level_file: str = "INFO"
    logger_error_file: str = "WARNING"

    messages: dict[str, Any] = dialogs

    price_map: dict[int, int] = Field(
        default_factory=lambda: {1: 70, 3: 160, 6: 300, 12: 600, 7: 0},
        description="Карта цен подписок по месяцам",
    )
    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),  # базовые значения
            str(BASE_DIR / ".env.local"),  # локальные переопределяют .env
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    def webhook_url(self) -> str:
        """Возвращает URL вебхука."""
        return f"{self.base_site}/webhook"

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


class SettingsDB(BaseSettings):
    """Конфигурация базы данных и Redis для проекта.

    Attributes
        db_host (str): Хост PostgreSQL-сервера. По умолчанию "localhost".
        db_port (int): Порт PostgreSQL-сервера. По умолчанию 5432.
        db_user (str): Имя пользователя для подключения к базе данных.
        db_password (SecretStr): Пароль пользователя для подключения к базе данных.
        db_database (str): Имя базы данных.
        redis_password (SecretStr): Пароль для подключения к Redis.
        redis_host (str): Хост Redis-сервера. По умолчанию "localhost".
        redis_port (int): Порт Redis-сервера. По умолчанию 6379.
        num_db (int): Номер базы данных Redis. По умолчанию 0.
        redis_user (str) : Имя пользователя Redis для приложения.
        default_expire (int) : Время жизни ключей в Redis по умолчанию (в секундах). По умолчанию 3600 секунд (1 час).
    Properties
        database_url (str): Строка подключения к PostgreSQL в формате
            `postgresql+asyncpg://user:password@host:port/database`.
            Формируется автоматически из указанных выше атрибутов.
        redis_url (str): Строка подключения к Redis в формате
            `redis://:password@host:port/db_number`.
    Configuration
        model_config (SettingsConfigDict): Конфигурация pydantic settings
            (путь до .env, кодировка и поведение при лишних переменных).

    """

    db_host: str = "postgres"
    db_port: int = 5432
    db_user: str
    db_password: SecretStr
    db_database: str

    redis_password: SecretStr
    redis_host: str = "redis"
    redis_port: int = 6379
    default_expire: int = 3600
    redis_user: str
    num_db: int = 0

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),  # базовые значения
            str(BASE_DIR / ".env.local"),  # локальные переопределяют .env
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    def database_url(self) -> str:
        """Строка подключения к PostgreSQL через asyncpg.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password.get_secret_value()}@"
            f"{self.db_host}:{self.db_port}/{self.db_database}"
        )

    @computed_field
    def redis_url(self) -> str:
        """Строка подключения к Redis.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"redis://{self.redis_user}:{self.redis_password.get_secret_value()}@"
            f"{self.redis_host}:{self.redis_port}/{self.num_db}"
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
        logger_level_file: str = "INFO",
        logger_error_file: str = "WARNING",
        extra_defaults: dict[str, Any] | None = None,
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
            diagnose=self.logger_level_stdout == "DEBUG",
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
            diagnose=self.logger_level_stdout == "DEBUG",
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
            diagnose=self.logger_level_stdout == "DEBUG",
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
    logger_level_stdout=settings_bot.logger_level_stdout,
    logger_level_file=settings_bot.logger_level_file,
    logger_error_file=settings_bot.logger_error_file,
)
# Инициализируем бота и диспетчер
bot: Bot = Bot(
    token=settings_bot.bot_token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
# Хранилище FSM
storage = RedisStorage.from_url(
    str(settings_db.redis_url),
    state_ttl=3600,  # ⏰ время жизни состояния (в секундах)
    data_ttl=3600,  # ⏰ время жизни данных FSM
)
# Это если работать без Redis
# dp = Dispatcher(storage=MemoryStorage())
# Это если работать через Redis
dp = Dispatcher(storage=storage)

if __name__ == "__main__":
    print(settings_bot)
    print(settings_bot.admin_ids)
    print(type(settings_bot.admin_ids))
    # print(settings_bot.parse_admin_ids("123456, 789012,345678"))
