from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import naming

APP_NAME = "ProjectDock"
APP_VERSION = "1.8.0"


def _gh_logged_in() -> bool:
    """是否检测到 gh CLI 登录态（settings 无令牌时的兜底）。"""
    if not shutil.which("gh"):
        return False
    try:
        import subprocess
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return r.returncode == 0
    except Exception:
        return False


def app_data_dir() -> Path:
    """应用数据目录：%APPDATA%/ProjectDock（Windows）。"""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _detect_library_root(start: Path) -> Path | None:
    """从 start 逐级向上查找「资料库」父目录：其下存在任一命名风格的项目文件夹即命中。"""
    for p in start.parents:
        try:
            if any(x.is_dir() and naming.parse_name(x.name) for x in p.iterdir()):
                return p
        except OSError:
            continue
    return None


def default_root() -> Path:
    """默认管理根目录：优先环境变量，其次向上探测「资料库」父目录，最后取当前目录。"""
    env = os.environ.get("PROJECTDOCK_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return _detect_library_root(Path(__file__).resolve()) or Path(os.getcwd())


class Settings:
    """持久化设置，保存在 settings.json。"""

    DEFAULTS = {
        "root": "",
        "agent": "pi",
        "theme": "system",
        "github_auto": True,
        "github_visibility": "private",
        "backup": True,
        "type_tabs": {},
        "confirm_policy": {"push": True, "delete": True, "github_create": True,
                           "release": True, "archive": True},
        "update_repo": "GinyvaXu/ProjectDock",
        "github_token": "",
        "naming_style": naming.STYLE_AUTO,
        "api_base_url": "https://api.deepseek.com",
        "api_model": "deepseek-chat",
        "api_key": "",
        "oc_model": "opencode-go/deepseek-v4.1-flash",
    }

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
        return self._data.get("agent", "pi")

    @property
    def theme(self) -> str:
        return self._data.get("theme", "system")

    @property
    def github_auto(self) -> bool:
        return bool(self._data.get("github_auto", True))

    @property
    def github_visibility(self) -> str:
        return self._data.get("github_visibility", "private")

    @property
    def backup(self) -> bool:
        return bool(self._data.get("backup", True))

    @property
    def type_tabs(self) -> dict:
        value = self._data.get("type_tabs", {})
        return value if isinstance(value, dict) else {}

    @property
    def confirm_policy(self) -> dict:
        value = self._data.get("confirm_policy", {})
        defaults = dict(self.DEFAULTS["confirm_policy"])
        if isinstance(value, dict):
            defaults.update({k: bool(v) for k, v in value.items()})
        return defaults

    def confirm_required(self, key: str) -> bool:
        """按确认策略判断某类操作是否需要用户确认（未配置默认按需确认）。"""
        return bool(self.confirm_policy.get(key, True))

    @property
    def github_token(self) -> str:
        return str(self._data.get("github_token") or "").strip()

    @property
    def update_repo(self) -> str:
        return str(self._data.get("update_repo") or "GinyvaXu/ProjectDock").strip() or "GinyvaXu/ProjectDock"

    @property
    def naming_style(self) -> str:
        """命名规范风格：auto / 已注册风格 id（见 naming.STYLES）。"""
        value = str(self._data.get("naming_style") or naming.STYLE_AUTO).strip().lower()
        if value == naming.STYLE_AUTO or value in naming.STYLES:
            return value
        return naming.STYLE_AUTO

    @property
    def api_base_url(self) -> str:
        """API 直连 Base URL（OpenAI 兼容，如 https://api.deepseek.com）。"""
        return str(self._data.get("api_base_url") or "").strip()

    @property
    def api_model(self) -> str:
        return str(self._data.get("api_model") or "").strip()

    @property
    def api_key(self) -> str:
        return str(self._data.get("api_key") or "").strip()

    @property
    def api_configured(self) -> bool:
        return bool(self.api_base_url and self.api_model and self.api_key)

    @property
    def oc_model(self) -> str:
        """opencode 会话模型（provider/model，如 opencode-go/deepseek-v4.1-flash）。"""
        return str(self._data.get("oc_model") or "opencode-go/deepseek-v4.1-flash").strip()

    def as_dict(self) -> dict:
        return {
            "root": str(self.root),
            "agent": self.agent,
            "theme": self.theme,
            "github_auto": self.github_auto,
            "github_visibility": self.github_visibility,
            "backup": self.backup,
            "type_tabs": self.type_tabs,
            "confirm_policy": self.confirm_policy,
            "update_repo": self.update_repo,
            "naming_style": self.naming_style,
            "api_base_url": self.api_base_url,
            "api_model": self.api_model,
            "api_key_set": bool(self.api_key),
            "api_configured": self.api_configured,
            "oc_model": self.oc_model,
            "github_logged_in": bool(self.github_token) or _gh_logged_in(),
        }

    def update(self, **kwargs) -> dict:
        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "root":
                self.root = value
            elif key in ("agent", "theme", "github_visibility"):
                self._data[key] = value
            elif key in ("github_auto", "backup"):
                self._data[key] = bool(value)
            elif key == "type_tabs":
                self._data[key] = value if isinstance(value, dict) else {}
            elif key == "confirm_policy":
                if isinstance(value, dict):
                    merged = dict(self.DEFAULTS["confirm_policy"])
                    merged.update({k: bool(v) for k, v in value.items()})
                    self._data[key] = merged
            elif key == "github_token":
                self._data[key] = str(value or "").strip()
            elif key == "update_repo":
                self._data[key] = str(value or "").strip() or "GinyvaXu/ProjectDock"
            elif key == "naming_style":
                text = str(value or "").strip().lower()
                if text == naming.STYLE_AUTO or text in naming.STYLES:
                    self._data[key] = text
            elif key in ("api_base_url", "api_model"):
                self._data[key] = str(value or "").strip()
            elif key == "api_key":
                self._data[key] = str(value or "").strip()
            elif key == "oc_model":
                self._data[key] = str(value or "").strip() or "opencode-go/deepseek-v4.1-flash"
        self.save()
        return self.as_dict()

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
