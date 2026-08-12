"""总控台聚合：跨项目收集 AI 操作日志等活动数据。"""
from __future__ import annotations

import json
from pathlib import Path

from .scanner import parse_project_dir


def collect_activity(root: Path, limit: int = 20) -> list[dict]:
    """跨项目合并最近的 AI 操作日志（时间倒序）。"""
    entries: list[dict] = []
    if not root.is_dir():
        return entries
    for project in sorted(root.iterdir()):
        if not project.is_dir() or not parse_project_dir(project.name):
            continue
        logs_dir = project / "logs" / "ai"
        if not logs_dir.is_dir():
            continue
        try:
            files = sorted(logs_dir.glob("*.json"), reverse=True)[:10]
        except OSError:
            continue
        for f in files:
            try:
                entry = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entry["project"] = project.name
            entry["project_path"] = str(project)
            entries.append(entry)
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return entries[:max(1, min(limit, 200))]