import builtins

import pytest
import yaml

from bot.dialogs.dialogs_text import load_dialogs


@pytest.mark.parametrize("filename", ["dummy.yaml"])
@pytest.mark.dialogs
def test_load_dialogs_success(monkeypatch, filename):
    # Мокаем open
    def mock_open(*args, **kwargs):
        from io import StringIO

        return StringIO("fake yaml content")

    monkeypatch.setattr(builtins, "open", mock_open)

    # Мокаем yaml.safe_load
    monkeypatch.setattr(
        yaml, "safe_load", lambda f: {"bot": {"general": {"echo": "Hello {text}"}}}
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
    def mock_open(*args, **kwargs):
        from io import StringIO

        return StringIO("bad yaml")

    monkeypatch.setattr(builtins, "open", mock_open)
    monkeypatch.setattr(
        yaml, "safe_load", lambda f: (_ for _ in ()).throw(yaml.YAMLError("bad yaml"))
    )

    with pytest.raises(yaml.YAMLError):
        load_dialogs("dummy.yaml")


@pytest.mark.dialogs
def test_load_dialogs_missing_bot_key(monkeypatch):
    def mock_open(*args, **kwargs):
        from io import StringIO

        return StringIO("yaml without bot key")

    monkeypatch.setattr(builtins, "open", mock_open)
    monkeypatch.setattr(yaml, "safe_load", lambda f: {"other": 123})

    with pytest.raises(KeyError):
        load_dialogs("dummy.yaml")
