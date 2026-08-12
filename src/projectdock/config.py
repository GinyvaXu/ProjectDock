from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "ProjectDock"
APP_VERSION = "0.1.0"


def app_data_dir() -> Path:
    """应用数据目录：%APPDATA%/ProjectDock（Windows）。"""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_root() -> Path:
    """默认管理根目录：优先环境变量，其次检测“资料库”式父目录，最后取当前目录。"""
    env = os.environ.get("PROJECTDOCK_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for p in here.parents:
        try:
            if any(x.is_dir() and x.name.startswith("项目") and "-" in x.name for x in p.iterdir()):
                return p
        except OSError:
            continue
    return Path(os.getcwd())


class Settings:
    """持久化设置，保存在 settings.json。"""

    DEFAULTS = {"root": "", "agent": "claude", "theme": "system"}

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or app_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "settings.json"
        self._data = dict(self.DEFAULTS)
        if self.path.exists():
            try:
                self._data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        if not self._data.get("root"):
            self._data["root"] = str(default_root())

    @property
    def root(self) -> Path:
        return Path(self._data["root"]).expanduser().resolve()

    @root.setter
    def root(self, value: str) -> None:
        self._data["root"] = str(Path(value).expanduser().resolve())

    @property
    def agent(self) -> str:
        return self._data.get("agent", "claude")

    @property
    def theme(self) -> str:
        return self._data.get("theme", "system")

    def as_dict(self) -> dict:
        return {"root": str(self.root), "agent": self.agent, "theme": self.theme}

    def update(self, **kwargs) -> dict:
        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "root":
                self.root = value
            elif key in ("agent", "theme"):
                self._data[key] = value
        self.save()
        return self.as_dict()

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
