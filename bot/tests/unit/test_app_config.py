import pytest

from shared.config import app_config
from shared.config.app_config import deep_merge, load_toml_config


def test_deep_merge_overrides_scalar_and_keeps_untouched_keys() -> None:
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    override = {"nested": {"x": 10}}

    result = deep_merge(base, override)

    assert result == {"a": 1, "nested": {"x": 10, "y": 2}}


def test_deep_merge_replaces_lists_wholesale() -> None:
    base = {"items": [1, 2, 3]}
    override = {"items": [9]}

    result = deep_merge(base, override)

    assert result == {"items": [9]}


def test_deep_merge_does_not_mutate_inputs() -> None:
    base = {"nested": {"x": 1}}
    override = {"nested": {"x": 2}}

    deep_merge(base, override)

    assert base == {"nested": {"x": 1}}


@pytest.fixture
def toml_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "BASE_DIR", tmp_path)
    (tmp_path / "app_config.toml").write_text(
        "scheduler_only_in_base = 'base'\n" "[section]\n" "x = 'base'\n" "y = 'base'\n"
    )
    return tmp_path


def test_base_only_loaded_on_prod(toml_dir, monkeypatch):
    monkeypatch.setenv("STAGE", "prod")

    config = load_toml_config()

    assert config["scheduler_only_in_base"] == "base"
    assert config["section"] == {"x": "base", "y": "base"}


def test_develop_stage_uses_dev_file_exclusively(toml_dir, monkeypatch):
    """prod и develop — разные окружения: develop не наследует ключи из base.

    `app_config.toml` и `app_config.develop.toml` описывают разные физические
    сервера (разные хосты, учётные данные, VPN-ноды) — поэтому develop не
    должен подхватывать то, чего нет в его собственном файле.
    """
    (toml_dir / "app_config.develop.toml").write_text("[section]\nx = 'dev'\n")
    monkeypatch.setenv("STAGE", "develop")

    config = load_toml_config()

    assert config["section"] == {"x": "dev"}
    assert "scheduler_only_in_base" not in config


def test_local_toml_applies_on_top_of_selected_stage(toml_dir, monkeypatch):
    """app_config.local.toml — личный оверрайд поверх выбранной стадии, для любого STAGE."""
    (toml_dir / "app_config.local.toml").write_text("[section]\nx = 'local'\n")
    monkeypatch.setenv("STAGE", "prod")

    config = load_toml_config()

    assert config["section"]["x"] == "local"
    assert config["section"]["y"] == "base"


def test_missing_base_config_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "BASE_DIR", tmp_path)
    monkeypatch.setenv("STAGE", "prod")

    with pytest.raises(FileNotFoundError):
        load_toml_config()


def test_missing_dev_config_raises_clear_error_on_non_prod_stage(toml_dir, monkeypatch):
    """STAGE=develop без app_config.develop.toml — явная ошибка, не тихий фоллбэк на base."""
    monkeypatch.setenv("STAGE", "develop")

    with pytest.raises(FileNotFoundError):
        load_toml_config()
