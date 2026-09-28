from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

_DB_LOCK = threading.RLock()


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
    excluded INTEGER NOT NULL DEFAULT 0,
    version_scheme TEXT NOT NULL DEFAULT ''
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
    with _DB_LOCK:
        return datetime.now().isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    with _DB_LOCK:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
        return conn


def _migrate(conn: sqlite3.Connection) -> None:
    with _DB_LOCK:
        """轻量迁移：为旧库补充新增列。"""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "excluded" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0")
        if "pinned" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        if "version_scheme" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN version_scheme TEXT NOT NULL DEFAULT ''")


def upsert_project(conn, project_id: str, name: str, ptype: str, path: str,
                   description: str = "", imported: bool = False, excluded: bool = False,
                   pinned: bool = False) -> None:
    with _DB_LOCK:
        ts = now()
    # 同路径被其它 id 占用（文件夹重命名/移动）：先清除旧注册，避免 UNIQUE(path) 冲突
        conn.execute("DELETE FROM projects WHERE path = ? AND id <> ?", (str(path), project_id))
        conn.execute(
            """INSERT INTO projects (id, name, type, path, description, created_at, updated_at, imported, excluded, pinned)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               name = excluded.name,
               type = excluded.type,
               path = excluded.path,
               description = excluded.description,
               updated_at = excluded.updated_at,
               imported = excluded.imported,
               excluded = excluded.excluded,
               pinned = excluded.pinned""",
            (project_id, name, ptype, str(path), description, ts, ts, 1 if imported else 0, 1 if excluded else 0,
             1 if pinned else 0),
        )
        conn.commit()


def get_project(conn, project_id: str) -> dict | None:
    with _DB_LOCK:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None


def list_projects(conn) -> list[dict]:
    with _DB_LOCK:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def set_pinned(conn, project_id: str, pinned: bool) -> None:
    """置顶/取消置顶项目。"""
    with _DB_LOCK:
        conn.execute("UPDATE projects SET pinned = ?, updated_at = ? WHERE id = ?",
                     (1 if pinned else 0, now(), project_id))
        conn.commit()


def set_version_scheme(conn, project_id: str, scheme: str) -> None:
    """设置项目级版本方案覆盖（'' = 跟随类型协议默认）。"""
    with _DB_LOCK:
        conn.execute("UPDATE projects SET version_scheme = ?, updated_at = ? WHERE id = ?",
                     (scheme or "", now(), project_id))
        conn.commit()


def delete_project(conn, project_id: str) -> None:
    with _DB_LOCK:
        """移除管理：标记 excluded=1，文件夹本身不动。重新导入即可恢复。"""
        conn.execute("UPDATE projects SET excluded = 1, updated_at = ? WHERE id = ?", (now(), project_id))
        conn.commit()


def list_custom_types(conn) -> list[dict]:
    with _DB_LOCK:
        rows = conn.execute("SELECT * FROM project_types ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def get_custom_type(conn, name: str) -> dict | None:
    with _DB_LOCK:
        row = conn.execute("SELECT * FROM project_types WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def upsert_custom_type(conn, name: str, label: str, description: str,
                       dirs: list[str], files: dict[str, str], git: bool) -> None:
    with _DB_LOCK:
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
    with _DB_LOCK:
        conn.execute("DELETE FROM project_types WHERE name = ?", (name,))
        conn.commit()
