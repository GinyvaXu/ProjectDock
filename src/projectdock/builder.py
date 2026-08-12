from __future__ import annotations

import sys
from pathlib import Path

PRIORITY = ["build_debug.py", "build_exe.py", "build_release.py", "build_setup_exe.py", "打包.bat"]
# scripts/ 目录下常见的构建/发布脚本名
SCRIPT_DIR_PATTERNS = ("build", "release", "archive", "package", "dist", "打包")


def _kind_for(suffix: str) -> str:
    if suffix == ".py":
        return "python"
    if suffix in (".js", ".mjs", ".cjs"):
        return "node"
    if suffix == ".ps1":
        return "ps1"
    if suffix in (".bat", ".cmd"):
        return "batch"
    return "other"


def find_build_scripts(project_path: Path) -> list[dict]:
    """发现项目根目录及 scripts/ 的构建脚本（build*.py / 打包.bat / scripts/build*.mjs 等）。"""
    if not project_path.is_dir():
        return []
    scripts = []
    seen = set()

    def add(path: Path):
        if path in seen:
            return
        seen.add(path)
        scripts.append({"name": path.name, "path": str(path), "kind": _kind_for(path.suffix.lower())})

    for p in sorted(project_path.iterdir()):
        if not p.is_file():
            continue
        if p.name == "打包.bat" or (p.name.startswith("build") and p.suffix in (".py", ".bat", ".cmd", ".ps1")):
            add(p)
    scripts_dir = project_path / "scripts"
    if scripts_dir.is_dir():
        for p in sorted(scripts_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix not in (".py", ".js", ".mjs", ".cjs", ".ps1", ".bat", ".cmd"):
                continue
            base = p.name.lower()
            if base.startswith(SCRIPT_DIR_PATTERNS):
                add(p)
    scripts.sort(key=lambda s: (PRIORITY.index(s["name"]) if s["name"] in PRIORITY else 99, s["name"]))
    return scripts


def command_for(script: dict) -> list[str]:
    """把脚本描述转成可执行命令。"""
    if script["kind"] == "python":
        return [sys.executable, script["path"]]
    if script["kind"] == "node":
        return ["node", script["path"]]
    if script["kind"] == "ps1":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script["path"]]
    if script["kind"] == "batch":
        return ["cmd", "/c", script["path"]]
    return [script["path"]]
