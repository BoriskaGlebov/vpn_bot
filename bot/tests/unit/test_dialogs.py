import builtins
from io import StringIO
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from bot.dialogs.dialogs_text import load_dialogs


@pytest.mark.parametrize("filename", ["dummy.yaml"])
@pytest.mark.dialogs
def test_load_dialogs_success(monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    """Проверяет успешную загрузку и парсинг YAML-файла с диалогами.

    Тест покрывает сценарий:
        - файл существует;
        - файл успешно читается;
        - YAML корректно парсится;
        - структура содержит ключ `bot`.

    Ожидается, что функция вернёт словарь диалогов без уровня `bot`.
    """

    def mock_open(self: Path, *args: Any, **kwargs: Any) -> StringIO:
        return StringIO("fake yaml content")

    # Эмулируем существование файла
    monkeypatch.setattr(Path, "exists", lambda self: True)

    # Подменяем открытие файла
    monkeypatch.setattr(Path, "open", mock_open)

    # Подменяем YAML-парсер
    monkeypatch.setattr(
        yaml,
        "safe_load",
        lambda f: {"bot": {"general": {"echo": "Hello {text}"}}},
    )

    result: dict[str, Any] = load_dialogs(filename)

    assert result["general"]["echo"] == "Hello {text}"


@pytest.mark.dialogs
def test_load_dialogs_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверяет поведение при отсутствии файла.

    Сценарий:
        - попытка открыть файл приводит к FileNotFoundError.

    Ожидается, что ошибка пробрасывается наружу.
    """

    def mock_open(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", mock_open)

    with pytest.raises(FileNotFoundError):
        load_dialogs("nonexistent.yaml")


@pytest.mark.dialogs
def test_load_dialogs_yaml_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверяет обработку ошибки парсинга YAML.

    Сценарий:
        - файл существует;
        - при парсинге возникает yaml.YAMLError.

    Ожидается, что ошибка не подавляется и пробрасывается.
    """

    def mock_open(self: Path, *args: Any, **kwargs: Any) -> StringIO:
        return StringIO("bad yaml")

    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "open", mock_open)

    # Генерируем исключение при вызове safe_load
    monkeypatch.setattr(
        yaml,
        "safe_load",
        lambda f: (_ for _ in ()).throw(yaml.YAMLError("bad yaml")),
    )

    with pytest.raises(yaml.YAMLError):
        load_dialogs("dummy.yaml")


@pytest.mark.dialogs
def test_load_dialogs_missing_bot_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверяет поведение при отсутствии обязательного ключа `bot`.

    Сценарий:
        - файл существует;
        - YAML успешно парсится;
        - но структура не содержит ключ `bot`.

    Ожидается, что будет выброшен KeyError.
    """

    def mock_open(self: Path, *args: Any, **kwargs: Any) -> StringIO:
        return StringIO("yaml without bot key")

    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "open", mock_open)

    # Возвращаем некорректную структуру
    monkeypatch.setattr(yaml, "safe_load", lambda f: {"other": 123})

    with pytest.raises(KeyError):
        load_dialogs("dummy.yaml")
