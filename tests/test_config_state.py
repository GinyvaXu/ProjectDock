from __future__ import annotations

import json

from projectdock.config import Settings
from projectdock.state import AppState


def test_settings_file_roundtrip(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "settings.json").write_text(json.dumps({"root": str(tmp_path / "r"), "agent": "pi", "theme": "dark"}), encoding="utf-8")
    settings = Settings(data_dir)
    assert settings.agent == "pi"
    assert settings.theme == "dark"
    assert str(settings.root).endswith("r")


def test_settings_update_root(tmp_path):
    data_dir = tmp_path / "data"
    settings = Settings(data_dir)
    new_root = tmp_path / "lib"
    new_root.mkdir()
    result = settings.update(root=str(new_root), theme="light")
    assert result["theme"] == "light"
    assert str(result["root"]).endswith("lib")
    assert Settings(data_dir).theme == "light"


def test_app_state_default(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("PROJECTDOCK_ROOT", str(tmp_path / "libroot"))
    (tmp_path / "libroot").mkdir()
    state = AppState.default()
    assert str(state.settings.root).endswith("libroot")
    assert (tmp_path / "appdata" / "ProjectDock" / "data.db").exists()
