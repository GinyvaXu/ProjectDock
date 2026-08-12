from __future__ import annotations

import sys
from pathlib import Path

PRIORITY = ["build_debug.py", "build_exe.py", "build_release.py", "build_setup_exe.py", "打包.bat"]


def find_build_scripts(project_path: Path) -> list[dict]:
    """发现项目根目录的构建脚本（build*.py / 打包.bat 等）。"""
    if not project_path.is_dir():
        return []
    scripts = []
    for p in sorted(project_path.iterdir()):
        if not p.is_file():
            continue
        if p.name == "打包.bat" or (p.name.startswith("build") and p.suffix in (".py", ".bat", ".cmd")):
            scripts.append({
                "name": p.name,
                "path": str(p),
                "kind": "python" if p.suffix == ".py" else "batch",
            })
    scripts.sort(key=lambda s: (PRIORITY.index(s["name"]) if s["name"] in PRIORITY else 99, s["name"]))
    return scripts


def command_for(script: dict) -> list[str]:
    """把脚本描述转成可执行命令。"""
    if script["kind"] == "python":
        return [sys.executable, script["path"]]
    return ["cmd", "/c", script["path"]]
