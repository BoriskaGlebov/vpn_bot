import builtins
from pathlib import Path

import pytest
import yaml

from bot.dialogs.dialogs_text import load_dialogs


@pytest.mark.parametrize("filename", ["dummy.yaml"])
@pytest.mark.dialogs
def test_load_dialogs_success(monkeypatch, filename):
    def mock_open(self, *args, **kwargs):
        from io import StringIO

        return StringIO("fake yaml content")

    # filename.exists() → True
    monkeypatch.setattr(Path, "exists", lambda self: True)

    # filename.open() → StringIO(...)
    monkeypatch.setattr(Path, "open", mock_open)

    # мок yaml.safe_load
    monkeypatch.setattr(
        yaml,
        "safe_load",
        lambda f: {"bot": {"general": {"echo": "Hello {text}"}}},
    )

    result = load_dialogs(filename)
    assert result["general"]["echo"] == "Hello {text}"


@pytest.mark.dialogs
def test_load_dialogs_file_not_found(monkeypatch):
    def mock_open(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", mock_open)

    with pytest.raises(FileNotFoundError):
        load_dialogs("nonexistent.yaml")


@pytest.mark.dialogs
def test_load_dialogs_yaml_error(monkeypatch):
    def mock_open(self, *args, **kwargs):
        from io import StringIO

        return StringIO("bad yaml")

    # делаем файл "существующим"
    monkeypatch.setattr(Path, "exists", lambda self: True)

    # мок файла
    monkeypatch.setattr(Path, "open", mock_open)

    # мок yaml.safe_load → бросает ошибку
    monkeypatch.setattr(
        yaml,
        "safe_load",
        lambda f: (_ for _ in ()).throw(yaml.YAMLError("bad yaml")),
    )

    with pytest.raises(yaml.YAMLError):
        load_dialogs("dummy.yaml")


@pytest.mark.dialogs
def test_load_dialogs_missing_bot_key(monkeypatch):
    def mock_open(self, *args, **kwargs):
        from io import StringIO

        return StringIO("yaml without bot key")

    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "open", mock_open)
    monkeypatch.setattr(yaml, "safe_load", lambda f: {"other": 123})

    with pytest.raises(KeyError):
        load_dialogs("dummy.yaml")
