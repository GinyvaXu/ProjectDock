from __future__ import annotations

import os
import stat as stat_module
from pathlib import Path

from . import naming, protocols
from .naming import ParsedProject, sanitize_title
from .versioning import read_version
from . import compliance

INVALID_CHARS = naming.INVALID_CHARS  # 兼容旧引用


def _is_alias(path: Path) -> bool:
    """目录联接 / 符号链接（同一实体的别名，不重复纳管）。"""
    try:
        if path.is_symlink():
            return True
        st = os.lstat(path)
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        return False


def parse_project_entry(name: str) -> ParsedProject | None:
    """解析文件夹名（兼容全部已注册命名风格），返回富解析结果；不符合返回 None。"""
    return naming.parse_name(name)


def parse_project_dir(name: str) -> tuple[int, str, str] | None:
    """解析项目文件夹名，返回 (序号, 类型, 名称)；不符合返回 None。

    兼容全部已注册风格；无类型风格（如 ProjectN-名称）的类型为空串（以注册表为准）。
    """
    entry = naming.parse_name(name)
    if entry is None:
        return None
    return (entry.index, entry.ptype, entry.title)


def find_next_index(root: Path, style_id: str | None = None) -> int:
    """扫描根目录中同风格项目的最大主序号 + 1。"""
    return naming.next_index(root, style_id)


def make_folder_name(root: Path, ptype: str, title: str, style_id: str | None = None) -> str:
    """按命名风格生成项目文件夹名（default: 按资料库自动识别）。"""
    return naming.make_folder_name(root, ptype, title, style_id)


def scan_root(root: Path, db_rows: dict[str, dict] | None = None, style_id: str | None = None) -> list[dict]:
    """扫描根目录下的项目文件夹（按命名风格；free 时纳管全部非点开头文件夹）。

    style_id 缺省/auto 时按资料库自动识别；严格风格下仅识别严格风格文件夹
    （其余文件夹由 list_unmanaged 提示手动导入）。
    """
    db_rows = db_rows or {}
    result: list[dict] = []
    if not root.is_dir():
        return result
    include_free = naming.resolve_style(root, style_id) == "free"
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or _is_alias(child):
            continue
        entry = naming.parse_name(child.name, include_free=include_free)
        if not entry:
            continue
        db = db_rows.get(child.name, {})
        if db.get("excluded"):
            continue
        # 无类型风格：类型以注册表（数据库）为准，未注册时归入「其他」
        ptype = entry.ptype or db.get("type") or "其他"
        title = entry.title
        override = db.get("version_scheme") or ""
        result.append({
            "id": child.name,
            "name": child.name,
            "type": ptype,
            "title": title,
            "path": str(child),
            "style": entry.style,
            "version_scheme": protocols.version_scheme_for(ptype, override),
            "version_scheme_set": override,
            "description": db.get("description", ""),
            "imported": bool(db.get("imported", False)),
            "pinned": bool(db.get("pinned", False)),
            "created_at": db.get("created_at", ""),
            "updated_at": db.get("updated_at", ""),
            "version": read_version(child),
            "has_git": (child / ".git").exists(),
            "has_logo": find_logo(child) is not None,
            "compliant": compliance.quick_compliance(child, ptype),
        })
    return result


def list_unmanaged(root: Path, db_rows: dict[str, dict] | None = None, style_id: str | None = None) -> list[dict]:
    """未纳管文件夹：不符合严格命名风格、且未导入/未移除的根目录文件夹。

    - 自由命名（free）下所有非点开头文件夹均已纳管，返回空；
    - 已导入（含用户主动移除）的不再提示；点开头目录始终排除。
    """
    db_rows = db_rows or {}
    out: list[dict] = []
    if not root.is_dir():
        return out
    if naming.resolve_style(root, style_id) == "free":
        return out
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith(".") or _is_alias(child):
            continue
        if naming.parse_name(child.name):
            continue
        if child.name in db_rows:
            continue  # 已导入或用户已移除（excluded）
        try:
            mtime = child.stat().st_mtime
        except OSError:
            mtime = 0.0
        out.append({"name": child.name, "path": str(child), "mtime": mtime})
    return out


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
    entry = naming.parse_name(folder.name)
    pid = folder.name
    title = entry.title if entry else folder.name
    if entry and entry.ptype:
        ptype = entry.ptype
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
