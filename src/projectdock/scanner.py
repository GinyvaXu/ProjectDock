from __future__ import annotations

import re
from pathlib import Path

from .versioning import read_version

INDEX_RE = re.compile(r"^项目(\d+)-")
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_title(title: str) -> str:
    """清理项目名：替换 Windows 非法字符、防路径穿越（..）、去首尾空白/点。"""
    title = INVALID_CHARS.sub("-", title or "")
    title = re.sub(r"\.\.+", "-", title)
    title = re.sub(r"\s+", " ", title).strip(" .-")
    return title or "未命名项目"


def parse_project_dir(name: str) -> tuple[int, str, str] | None:
    """解析 项目NN-类型-名称，返回 (序号, 类型, 名称)；不符合返回 None。"""
    m = INDEX_RE.match(name)
    if not m:
        return None
    index = int(m.group(1))
    rest = name[len(m.group(0)):]
    if "-" not in rest:
        return index, rest, rest
    ptype, _, title = rest.partition("-")
    return index, ptype, title or rest


def find_next_index(root: Path) -> int:
    """扫描根目录中 项目NN-* 的最大序号 + 1。"""
    best = 0
    if not root.is_dir():
        return 1
    for child in root.iterdir():
        if not child.is_dir():
            continue
        parsed = parse_project_dir(child.name)
        if parsed:
            best = max(best, parsed[0])
    return best + 1


def make_folder_name(root: Path, ptype: str, title: str) -> str:
    """生成 项目NN-类型-名称 文件夹名（沿用资料库不补零的命名习惯）。"""
    return f"项目{find_next_index(root)}-{ptype}-{sanitize_title(title)}"


def scan_root(root: Path, db_rows: dict[str, dict] | None = None) -> list[dict]:
    """扫描根目录下的 项目NN-* 文件夹，并与注册表合并元数据。"""
    db_rows = db_rows or {}
    result: list[dict] = []
    if not root.is_dir():
        return result
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        parsed = parse_project_dir(child.name)
        if not parsed:
            continue
        _, ptype, title = parsed
        db = db_rows.get(child.name, {})
        if db.get("excluded"):
            continue
        result.append({
            "id": child.name,
            "name": child.name,
            "type": ptype,
            "title": title,
            "path": str(child),
            "description": db.get("description", ""),
            "imported": bool(db.get("imported", False)),
            "created_at": db.get("created_at", ""),
            "updated_at": db.get("updated_at", ""),
            "version": read_version(child),
            "has_git": (child / ".git").exists(),
        })
    return result


def import_folder(conn, folder_path: Path, ptype: str, description: str) -> dict:
    """把已有文件夹纳入管理（注册到数据库）。"""
    folder = Path(folder_path).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("路径不是有效文件夹")
    parsed = parse_project_dir(folder.name)
    pid = folder.name
    title = parsed[2] if parsed else folder.name
    if parsed:
        ptype = parsed[1]
    from .db import upsert_project

    upsert_project(conn, pid, folder.name, ptype, str(folder), description, imported=True)
    return {
        "id": pid,
        "name": folder.name,
        "type": ptype,
        "title": title,
        "path": str(folder),
        "description": description,
        "imported": True,
    }
