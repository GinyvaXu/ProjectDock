from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

GITIGNORE_SOFTWARE = """# Python 缓存
__pycache__/
*.pyc
build/
dist/
versions/
installer/
.venv/
venv/
.env
logs/
.idea/
.vscode/
"""

GITIGNORE_BASIC = """# 缓存与临时文件
__pycache__/
*.pyc
.DS_Store
.idea/
.vscode/
"""

README_SOFTWARE = """# {title}

{description}

## 技术栈
- Python 3.12

## 快速开始
```bash
python -m pip install -r requirements.txt
python run.py
```

## 测试
```bash
python -m pytest
```

## 版本与构建
- 版本号唯一来源：VERSION 文件；更新内容记录在 CHANGELOG.md
- 构建产物归档到 versions/vX.Y.Z/dist/（仅本地保留，不上传）
"""

README_BASIC = """# {title}

{description}

## 说明
本目录由 ProjectDock 项目坞初始化创建。
"""

README_WEBSITE = """# {title}

{description}

## 结构
- index.html  — 首页
- assets/     — 静态资源（css/js/img）
"""

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 40px; color: #1d1d1f; }}
    h1 {{ font-size: 2rem; letter-spacing: -0.02em; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{description}</p>
</body>
</html>
"""

MAIN_PY = """import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main() -> int:
    print("{title} 脚本运行中……")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

CHANGELOG_TEMPLATE = """# 更新日志

## [0.1.0] - 2026-08-12
### Added
- 项目初始化（由 ProjectDock 预设生成）
"""

AGENTS_SOFTWARE = """# AGENTS.md

{description}

## 运行与测试
- 测试：python -m pytest
- 构建：python build_debug.py / build_exe.py（产物进 versions/vX.Y.Z/dist/）

## 版本规范
- 版本号唯一来源：VERSION 文件
- 提交前缀：feat: / fix: / release: / build: / chore: / docs:
- 单 main 分支直接开发与发布；不主动 push
"""

GODOT_README = """# {title}

{description}

## 引擎
- Godot 4.x（由 ProjectDock 游戏类型预设创建，请在 Godot 中打开本目录作为项目）

## 建议结构
- scenes/  场景
- scripts/ GDScript
- assets/  素材（精灵/音频/字体）
"""


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
}

# 各类型的默认菜单模板（可在设置中覆盖）
DEFAULT_TABS = {
    "软件": ["overview", "versions", "compliance", "ai", "ailog"],
    "网站": ["overview", "versions", "compliance", "ai", "ailog"],
    "游戏": ["overview", "versions", "compliance", "ai", "ailog"],
    "脚本": ["overview", "versions", "compliance", "ai", "ailog"],
    "其他": ["overview", "versions", "compliance", "ai", "ailog"],
    "PPT": ["overview", "docs", "ai", "ailog"],
    "文稿": ["overview", "docs", "ai", "ailog"],
}

ALL_TAB_KEYS = tuple(TAB_LABELS)


def tabs_for_type(ptype: str, override: dict | None = None) -> list[str]:
    """返回类型的 Tab 模板；override 来自设置（type_tabs）。"""
    tabs = list(DEFAULT_TABS.get(ptype, DEFAULT_TABS["其他"]))
    if override and isinstance(override, dict):
        custom = override.get(ptype)
        if isinstance(custom, list) and custom:
            tabs = [t for t in custom if t in TAB_LABELS]
    if "overview" not in tabs:
        tabs = ["overview"] + tabs
    if "ailog" not in tabs:
        tabs = tabs + ["ailog"]
    return tabs


PRESETS: dict[str, dict] = {
    "软件": {
        "label": "软件",
        "description": "Python 软件项目骨架：README/VERSION/CHANGELOG/测试/构建规范",
        "git": True,
        "dirs": ["src", "tests"],
        "files": {
            "README.md": README_SOFTWARE,
            "VERSION": "0.1.0\n",
            "CHANGELOG.md": CHANGELOG_TEMPLATE,
            "requirements.txt": "# 依赖\n",
            ".gitignore": GITIGNORE_SOFTWARE,
            "AGENTS.md": AGENTS_SOFTWARE,
        },
    },
    "网站": {
        "label": "网站",
        "description": "静态网站骨架：index.html + assets/",
        "git": True,
        "dirs": ["assets/css", "assets/js", "assets/img"],
        "files": {
            "README.md": README_WEBSITE,
            "index.html": INDEX_HTML,
            ".gitignore": GITIGNORE_BASIC,
        },
    },
    "游戏": {
        "label": "游戏",
        "description": "Godot 4 游戏骨架：推荐目录结构",
        "git": True,
        "dirs": ["scenes", "scripts", "assets/sprites", "assets/audio", "assets/fonts"],
        "files": {
            "README.md": GODOT_README,
            ".gitignore": GITIGNORE_BASIC,
        },
    },
    "PPT": {
        "label": "PPT",
        "description": "演示文稿目录：素材/输出 分离",
        "git": False,
        "dirs": ["素材", "输出", "参考"],
        "files": {"README.md": README_BASIC},
    },
    "文稿": {
        "label": "文稿",
        "description": "文稿/文档目录：docs 结构",
        "git": False,
        "dirs": ["docs"],
        "files": {"README.md": README_BASIC},
    },
    "脚本": {
        "label": "脚本",
        "description": "Python 脚本工具骨架：main.py",
        "git": True,
        "dirs": ["scripts"],
        "files": {
            "README.md": README_BASIC,
            "main.py": MAIN_PY,
            ".gitignore": GITIGNORE_BASIC,
        },
    },
    "其他": {
        "label": "其他",
        "description": "通用目录：README + git",
        "git": True,
        "dirs": [],
        "files": {"README.md": README_BASIC, ".gitignore": GITIGNORE_BASIC},
    },
}


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
