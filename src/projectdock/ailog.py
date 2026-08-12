"""AI 操作日志。

每个项目在 logs/ai/ 下保存 JSON 日志（logs/ 已被 gitignore，仅本地保留）。
外部 agent（codex/claude/pi）按项目契约主动写入；App 内任务自动记录。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

LOG_SUBDIR = "ai"
VALID_RESULTS = ("running", "done", "failed")


def log_dir(project_path: Path) -> Path:
    return project_path / "logs" / LOG_SUBDIR


def _slug(agent: str) -> str:
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", agent or "agent")
    return s[:40] or "agent"


def write_log(project_path: Path, *, agent: str, action: str, result: str,
              summary: str = "", details: str = "", source: str = "external",
              git: dict | None = None, backup: str = "") -> Path:
    """写一条 AI 操作日志，返回日志文件路径。result ∈ running/done/failed。"""
    if result not in VALID_RESULTS:
        result = "done"
    d = log_dir(project_path)
    d.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent": agent or "unknown",
        "source": "external" if source != "inapp" else "inapp",
        "action": action or "",
        "result": result,
        "summary": summary or "",
        "details": details or "",
        "git": git or {},
        "backup": backup or "",
    }
    fname = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns()}_{_slug(agent)}.json"
    path = d / fname
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_logs(project_path: Path, limit: int = 50) -> list[dict]:
    """按时间倒序返回最近 limit 条日志。"""
    d = log_dir(project_path)
    if not d.is_dir():
        return []
    out: list[dict] = []
    try:
        files = sorted(d.glob("*.json"), reverse=True)
    except OSError:
        return out
    for f in files:
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entry["file"] = f.name
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def recent_summary(project_path: Path, limit: int = 3) -> list[str]:
    """最近若干条日志的一行摘要（供 agent 动态上下文使用）。"""
    return [
        f"[{e.get('ts', '')[:16]}] {e.get('agent', '')}: {e.get('action', '')} → {e.get('result', '')}"
        for e in list_logs(project_path, limit)
    ]