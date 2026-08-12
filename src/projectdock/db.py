from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT '其他',
    path TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    imported INTEGER NOT NULL DEFAULT 0,
    excluded INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS project_types (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT DEFAULT '',
    dirs TEXT NOT NULL DEFAULT '[]',
    files TEXT NOT NULL DEFAULT '{}',
    git INTEGER NOT NULL DEFAULT 1
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """轻量迁移：为旧库补充新增列。"""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "excluded" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0")


def upsert_project(conn, project_id: str, name: str, ptype: str, path: str,
                   description: str = "", imported: bool = False, excluded: bool = False) -> None:
    ts = now()
    conn.execute(
        """INSERT INTO projects (id, name, type, path, description, created_at, updated_at, imported, excluded)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
             id = excluded.id,
             name = excluded.name,
             type = excluded.type,
             description = excluded.description,
             updated_at = excluded.updated_at,
             imported = excluded.imported,
             excluded = excluded.excluded""",
        (project_id, name, ptype, str(path), description, ts, ts, 1 if imported else 0, 1 if excluded else 0),
    )
    conn.commit()


def get_project(conn, project_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def list_projects(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_project(conn, project_id: str) -> None:
    """移除管理：标记 excluded=1，文件夹本身不动。重新导入即可恢复。"""
    conn.execute("UPDATE projects SET excluded = 1, updated_at = ? WHERE id = ?", (now(), project_id))
    conn.commit()


def list_custom_types(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM project_types ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_custom_type(conn, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM project_types WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def upsert_custom_type(conn, name: str, label: str, description: str,
                       dirs: list[str], files: dict[str, str], git: bool) -> None:
    import json

    conn.execute(
        """INSERT INTO project_types (name, label, description, dirs, files, git)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             label = excluded.label,
             description = excluded.description,
             dirs = excluded.dirs,
             files = excluded.files,
             git = excluded.git""",
        (name, label, description, json.dumps(dirs, ensure_ascii=False), json.dumps(files, ensure_ascii=False), 1 if git else 0),
    )
    conn.commit()


def delete_custom_type(conn, name: str) -> None:
    conn.execute("DELETE FROM project_types WHERE name = ?", (name,))
    conn.commit()
