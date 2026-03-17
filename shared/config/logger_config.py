import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger


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
