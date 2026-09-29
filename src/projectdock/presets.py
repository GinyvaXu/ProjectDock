from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import protocols
from .protocols import (  # noqa: F401 - 兼容旧引用（模板常量）
    AGENTS_SOFTWARE, CHANGELOG_TEMPLATE, GITIGNORE_BASIC, GITIGNORE_SOFTWARE,
    GODOT_README, INDEX_HTML, MAIN_PY, README_APP, README_BASIC, README_BATCH,
    README_DATA, README_SOFTWARE, README_WEBSITE, USAGE_APP,
)


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "_", title.strip()).strip("_")
    return s.lower() or "app"


TAB_LABELS = {
    "overview": "概览",
    "versions": "版本与构建",
    "compliance": "合规",
    "docs": "文稿版本",
    "ai": "AI 管理",
    "ailog": "AI 日志",
    "github": "GitHub 仓库",
    "techstack": "技术栈",
}

# 各类型的默认菜单模板（来自管理协议，可在设置中覆盖）
DEFAULT_TABS = {name: list(proto.tabs) for name, proto in protocols.PROTOCOLS.items()}

ALL_TAB_KEYS = tuple(TAB_LABELS)


# 新版本新增的默认 Tab（仅自动并入这些，尊重用户对其它 Tab 的删除）
NEW_TABS = ("github", "techstack")


def tabs_for_type(ptype: str, override: dict | None = None) -> list[str]:
    """返回类型的 Tab 模板；override 来自设置（type_tabs）。

    注：AI 日志已并入「AI」栏目（子页签），不再单独作为默认 Tab；
    旧版本保存的 ailog/compliance 覆盖仍按用户意愿保留。
    """
    tabs = list(DEFAULT_TABS.get(ptype, DEFAULT_TABS["其他"]))
    if override and isinstance(override, dict):
        custom = override.get(ptype)
        if isinstance(custom, list) and custom:
            tabs = [t for t in custom if t in TAB_LABELS]
    if "overview" not in tabs:
        tabs = ["overview"] + tabs
    # 新版本新增的默认 Tab（如 github）自动并入用户已保存的模板；
    # 只并入 NEW_TABS，避免覆盖用户主动删除的旧 Tab（如 docs）
    default = DEFAULT_TABS.get(ptype, DEFAULT_TABS["其他"])
    missing = [k for k in default if k in NEW_TABS and k not in tabs]
    if missing:
        pos = tabs.index("overview") + 1 if "overview" in tabs else len(tabs)
        for key in reversed(missing):
            tabs.insert(pos, key)
    return tabs


# 类型预设（骨架）＝管理协议派生；完整协议定义见 protocols.py
PRESETS: dict[str, dict] = {name: proto.as_preset() for name, proto in protocols.PROTOCOLS.items()}


def apply_preset(project_path: Path, ptype: str, title: str, description: str = "",
                 git: bool = True, git_identity: dict | None = None) -> dict:
    """按内置类型在 project_path 生成骨架文件，并可选 git init + 首次提交。"""
    spec = PRESETS.get(ptype) or PRESETS["其他"]
    return _apply_spec(project_path, spec, ptype, title, description, git, git_identity)


def apply_custom_preset(project_path: Path, spec: dict, title: str, description: str = "",
                        git: bool = True, git_identity: dict | None = None) -> dict:
    """按自定义类型模板（dirs/files/git）生成骨架。spec 来自数据库 project_types。"""
    return _apply_spec(project_path, spec, spec.get("label") or spec.get("name") or "自定义", title, description, git, git_identity)


def _apply_spec(project_path: Path, spec: dict, ptype: str, title: str, description: str,
                git: bool, git_identity: dict | None) -> dict:
    project_path.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for rel in spec.get("dirs", []):
        if rel:
            (project_path / rel).mkdir(parents=True, exist_ok=True)
            created.append(rel + "/")
    package = _slug(title)
    for rel, template in spec.get("files", {}).items():
        target = project_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == "AGENTS.md":
            from .contract import contract_for
            content = contract_for(ptype, spec, title, description)
        else:
            content = template.format(title=title, description=description, package=package)
        target.write_text(content, encoding="utf-8")
        created.append(rel)
    git_ok = False
    message = "预设初始化完成"
    if git and spec.get("git", True):
        git_ok = _git_init_commit(project_path, git_identity)
        message = "预设初始化完成（含 git 首次提交）" if git_ok else "预设初始化完成，但 git 初始化失败"
    return {"type": ptype, "files": created, "git": git_ok, "message": message}


def ensure_git_commit(project_path: Path, identity: dict | None = None) -> bool:
    """确保目录已 git init 且有至少一个提交；已存在仓库则直接返回 True。"""
    if (project_path / ".git").is_dir():
        return True
    return _git_init_commit(project_path, identity)


def _git_init_commit(project_path: Path, identity: dict | None = None) -> bool:
    try:
        env = os.environ.copy()
        if identity:
            env.update({
                "GIT_AUTHOR_NAME": identity.get("name", "ProjectDock"),
                "GIT_AUTHOR_EMAIL": identity.get("email", "projectdock@local"),
                "GIT_COMMITTER_NAME": identity.get("name", "ProjectDock"),
                "GIT_COMMITTER_EMAIL": identity.get("email", "projectdock@local"),
            })
        subprocess.run(["git", "init", "-b", "main"], cwd=str(project_path), check=True,
                       capture_output=True, env=env, creationflags=0x08000000 if os.name == "nt" else 0)
        subprocess.run(["git", "add", "."], cwd=str(project_path), check=True,
                       capture_output=True, env=env, creationflags=0x08000000 if os.name == "nt" else 0)
        subprocess.run(["git", "commit", "-m", "chore: 项目初始化"], cwd=str(project_path), check=True,
                       capture_output=True, env=env, creationflags=0x08000000 if os.name == "nt" else 0)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False
