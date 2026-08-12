from __future__ import annotations

import os
import re
from pathlib import Path

from .versioning import read_version
from . import compliance

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
            "has_logo": find_logo(child) is not None,
            "compliant": compliance.quick_compliance(child, ptype),
        })
    return result


LOGO_CANDIDATES = [
    "logo.png", "logo.jpg", "logo.jpeg", "logo.webp", "logo.svg",
    "icon.png", "icon.jpg", "icon.jpeg", "icon.ico", "appicon.png",
    "favicon.png", "favicon.ico", "图标.png", "图标.jpg",
    "assets/logo.png", "assets/icon.png", "static/logo.png", "static/icon.png",
    "images/logo.png", "img/logo.png", "src/logo.png", "src/icon.png",
]

DOC_SKIP_TOP = {".git", "versions", "dist", "build", ".venv", "venv", "__pycache__", "node_modules", "logs", "installer", ".idea", ".vscode"}
DOC_EXTENSIONS = {".md", ".txt", ".doc", ".docx", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls"}
DOC_KEYWORDS = ("计划书", "企划书", "方案", "设计", "需求", "说明书", "提案", "立项", "可行性")


def find_logo(project_path: Path) -> Path | None:
    """在项目内查找 logo/图标文件，找不到返回 None。"""
    for rel in LOGO_CANDIDATES:
        cand = project_path / rel
        if cand.is_file():
            return cand
    return None


def find_documents(project_path: Path, max_depth: int = 2) -> list[dict]:
    """扫描项目内的计划书/企划书/方案/设计等文档（根目录 + 有限深度子目录）。"""
    docs: list[dict] = []
    if not project_path.is_dir():
        return docs
    for dirpath, dirnames, filenames in os.walk(project_path):
        rel = Path(dirpath).relative_to(project_path)
        depth = len(rel.parts)
        if rel.parts and rel.parts[0] in DOC_SKIP_TOP:
            dirnames[:] = []
            continue
        if depth > max_depth:
            dirnames[:] = []
            continue
        for name in filenames:
            lower = name.lower()
            if lower == "readme.md":
                docs.append({"name": name, "path": str(Path(dirpath) / name), "kind": "readme"})
                continue
            if Path(name).suffix.lower() in DOC_EXTENSIONS and any(k in name for k in DOC_KEYWORDS):
                docs.append({"name": name, "path": str(Path(dirpath) / name), "kind": Path(name).suffix.lower().lstrip(".")})

    def sort_key(d: dict):
        n = d["name"].lower()
        if n == "readme.md":
            return (0, n)
        if "计划书" in d["name"] or "企划书" in d["name"]:
            return (1, n)
        if any(k in d["name"] for k in ("方案", "设计", "需求", "说明书", "提案", "立项")):
            return (2, n)
        return (3, n)

    docs.sort(key=sort_key)
    return docs


DOC_GROUP_EXT = {".docx": "Word 文档", ".doc": "Word 文档", ".pdf": "PDF", ".pptx": "PPT",
                  ".ppt": "PPT", ".xlsx": "表格", ".xls": "表格", ".md": "Markdown", ".txt": "文本"}


def scan_documents(project_path: Path, max_depth: int = 3) -> list[dict]:
    """扫描项目内全部文档（按文件类型分组排序），供「文稿版本」等类型模板使用。

    返回 [{name, path, ext, group, size, mtime}]，按 类型组 → 修改时间倒序 排序。
    """
    if not project_path.is_dir():
        return []
    docs: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(project_path):
        rel = Path(dirpath).relative_to(project_path)
        if rel.parts and rel.parts[0] in DOC_SKIP_TOP:
            dirnames[:] = []
            continue
        if len(rel.parts) > max_depth:
            dirnames[:] = []
            continue
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext not in DOC_GROUP_EXT:
                continue
            full = Path(dirpath) / name
            try:
                size = full.stat().st_size
                mtime = full.stat().st_mtime
            except OSError:
                size, mtime = None, 0.0
            docs.append({"name": name, "path": str(full), "ext": ext.lstrip("."),
                         "group": DOC_GROUP_EXT[ext], "size": size, "mtime": mtime})
    order = {g: i for i, g in enumerate(DOC_GROUP_EXT.values())}
    docs.sort(key=lambda d: (order.get(d["group"], 99), -(d["mtime"] or 0)))
    return docs


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
