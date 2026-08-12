from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def gh_available() -> bool:
    return shutil.which("gh") is not None


def repo_name_for(title: str) -> str:
    """把项目名转成 GitHub 仓库名（保留 Unicode 字母数字，分隔符用 -）。"""
    s = re.sub(r"[^\w\-]+", "-", title.strip(), flags=re.UNICODE).strip("-")
    return s or "project"


def has_remote(project_path: Path) -> bool:
    if not (project_path / ".git").is_dir():
        return False
    try:
        r = subprocess.run(["git", "remote"], cwd=str(project_path), capture_output=True, text=True, timeout=15,
                        creationflags=0x08000000 if os.name == "nt" else 0)
        return "origin" in r.stdout.split()
    except (subprocess.TimeoutExpired, OSError):
        return False


def create_repo(project_path: Path, name: str, visibility: str = "private", owner: str | None = None) -> dict:
    """自动创建 GitHub 仓库并推送（gh repo create --source=. --remote=origin --push）。"""
    if not gh_available():
        return {"ok": False, "message": "未检测到 gh 命令"}
    full = f"{owner}/{name}" if owner else name
    flag = "--private" if visibility == "private" else "--public"
    cmd = ["gh", "repo", "create", full, flag, "--source=.", "--remote=origin", "--push"]
    try:
        r = subprocess.run(cmd, cwd=str(project_path), capture_output=True, text=True, timeout=180,
                        creationflags=0x08000000 if os.name == "nt" else 0)
        if r.returncode == 0:
            return {"ok": True, "message": r.stdout.strip() or f"已创建并推送 {full}"}
        return {"ok": False, "message": (r.stderr or r.stdout).strip() or "gh repo create 失败"}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "message": str(exc)}
