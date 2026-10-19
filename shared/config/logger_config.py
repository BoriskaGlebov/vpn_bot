import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from shared.config.context import patch_record


class LoggerConfig:
    """Настройка логирования с использованием loguru.

    Args:
        log_dir (Path): Путь к директории для хранения логов.
        logger_level_stdout (str, optional): Уровень логирования для вывода в stdout. Defaults to "INFO".
        logger_level_file (str, optional): Уровень логирования для основного файла лога. Defaults to "DEBUG".
        logger_error_file (str, optional): Уровень логирования для файла ошибок. Defaults to "ERROR".
        diagnose_files (bool, optional): Включать ли `diagnose` (печать значений
            переменных из фреймов стека в трейсбеке) для файловых обработчиков
            (`file.log`, `error.log`). Эти файлы хранятся 30 дней и попадают в
            бэкапы, поэтому по умолчанию выключено — независимо от уровня
            логирования в stdout. Defaults to False.
        extra_defaults (Optional[Dict[str, Any]], optional): Значения по умолчанию для extra полей. Defaults to None.

    """

    def __init__(
        self,
        log_dir: Path,
        logger_level_stdout: str = "INFO",
        logger_level_file: str = "INFO",
        logger_error_file: str = "WARNING",
        diagnose_files: bool = False,
        extra_defaults: dict[str, Any] | None = None,
    ) -> None:
        self.log_dir = log_dir
        self.logger_level_stdout = logger_level_stdout
        self.logger_level_file = logger_level_file
        self.logger_error_file = logger_error_file
        self.diagnose_files = diagnose_files
        self.extra_defaults = extra_defaults or {"user": "undefined_user"}

        self._ensure_log_dir_exists()
        self._setup_logging()

    def _ensure_log_dir_exists(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

    @staticmethod
    def _user_filter(record: Mapping[str, Any]) -> bool:
        user = record.get("extra", {}).get("user")
        return bool(user and user != "undefined_user")

    @staticmethod
    def _default_filter(record: Mapping[str, Any]) -> bool:
        user = record.get("extra", {}).get("user")
        return user in (None, "undefined_user")

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
        return (
            self._user_filter(record) or self._default_filter(record)
        ) and self._exclude_errors(record)

    def _setup_logging(self) -> None:
        logger.remove()
        logger.configure(
            extra=self.extra_defaults,
            patcher=patch_record,
        )
        self._add_stdout_handler()
        self._add_file_handlers()

    def _add_stdout_handler(self) -> None:
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
            diagnose=self.diagnose_files,
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
            diagnose=self.diagnose_files,
            filter=lambda r: self._user_filter(r) or self._default_filter(r),
            enqueue=True,
        )

    @staticmethod
    def _get_format() -> str:
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - "
            "<level>{level:^10}</level> - "
            "<cyan>{name}</cyan>:<magenta>{line}</magenta> - "
            "<yellow>{function}</yellow> - "
            "<magenta>{extra[user]:^15}</magenta> - "
            "<white>{message}</white>"
        )
