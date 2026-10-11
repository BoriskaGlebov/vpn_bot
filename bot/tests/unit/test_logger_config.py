from pathlib import Path

from loguru import logger

from shared.config.logger_config import LoggerConfig


def _diagnose_by_sink(tmp_path: Path) -> dict[str, bool]:
    """Собирает значение diagnose для каждого обработчика по типу sink."""
    result: dict[str, bool] = {}
    for handler in logger._core.handlers.values():
        formatter = handler._exception_formatter
        sink = handler._sink
        if type(sink).__name__ == "StreamSink":
            result["stdout"] = formatter._diagnose
        elif type(sink).__name__ == "FileSink":
            name = str(sink._file.name)
            if name.endswith("error.log"):
                result["error.log"] = formatter._diagnose
            elif name.endswith("file.log"):
                result["file.log"] = formatter._diagnose
    return result


def test_diagnose_files_defaults_to_false_even_with_debug_stdout(
    tmp_path: Path,
) -> None:
    """LOGGER_LEVEL_STDOUT=DEBUG не должен включать diagnose для файловых логов."""
    LoggerConfig(log_dir=tmp_path, logger_level_stdout="DEBUG")

    diagnose = _diagnose_by_sink(tmp_path)

    assert diagnose["stdout"] is True
    assert diagnose["file.log"] is False
    assert diagnose["error.log"] is False


def test_diagnose_files_can_be_enabled_explicitly(tmp_path: Path) -> None:
    LoggerConfig(log_dir=tmp_path, logger_level_stdout="INFO", diagnose_files=True)

    diagnose = _diagnose_by_sink(tmp_path)

    assert diagnose["stdout"] is False
    assert diagnose["file.log"] is True
    assert diagnose["error.log"] is True
