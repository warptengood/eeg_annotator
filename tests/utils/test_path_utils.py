import sys
from pathlib import Path

from src.utils.path_utils import resource_path


def test_dev_mode_resolves_to_project_root():
    # In dev mode (no _MEIPASS), base is 3 levels up from src/utils/
    # i.e., the project root
    result = resource_path("resources/montages")
    assert result.is_dir(), f"Expected directory at {result}"
    assert result.parent.parent.name != "src", "Should resolve to project root"


def test_returns_path_object_by_default():
    result = resource_path("resources/montages")
    assert isinstance(result, Path)


def test_to_string_returns_str():
    result = resource_path("resources/montages", to_string=True)
    assert isinstance(result, str)


def test_to_string_path_matches_path_object():
    path_obj = resource_path("resources/montages")
    path_str = resource_path("resources/montages", to_string=True)
    assert str(path_obj) == path_str


def test_bundle_mode_uses_meipass(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "bundle"
    fake_bundle.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_bundle), raising=False)
    result = resource_path("resources/montages")
    assert result == fake_bundle / "resources/montages"


def test_bundle_mode_to_string(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "bundle"
    fake_bundle.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_bundle), raising=False)
    result = resource_path("resources/icons", to_string=True)
    assert result == str(fake_bundle / "resources/icons")
