"""ProjectDock 构建辅助：读取 VERSION（版本号唯一来源）、准备版本目录、归档旧产物。"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def current_version() -> str:
    """从 VERSION 文件读取当前版本。"""
    v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not v:
        raise SystemExit("VERSION 文件为空")
    return v


def version_dir() -> Path:
    """versions/vX.Y.Z/ 目录（仅本地保留，不入库）。"""
    d = ROOT / "versions" / f"v{current_version()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def prepare_dist() -> Path:
    d = version_dir() / "dist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def archive_old_exes(keep: int = 1) -> list[str]:
    """把根 dist/ 中较旧的产物按时间戳归档进当前版本目录。"""
    dist = ROOT / "dist"
    if not dist.is_dir():
        return []
    archived: list[str] = []
    old = sorted(dist.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
    for f in old:
        target = prepare_dist() / f"{f.stem}_old_{int(f.stat().st_mtime)}{f.suffix}"
        shutil.move(str(f), str(target))
        archived.append(str(target))
    return archived
