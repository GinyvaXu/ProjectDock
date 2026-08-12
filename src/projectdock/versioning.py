from __future__ import annotations

import re
from pathlib import Path

VERSION_RE = re.compile(r"^\s*v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s*$")
CHANGELOG_HEAD_RE = re.compile(r"^##\s*\[?(v?[\d.]+[^\]]*)\]?\s*(?:-\s*(.+))?$", re.IGNORECASE)
CHANGELOG_GROUP_RE = re.compile(r"^###\s+(.+)$")


def read_version(project_path: Path) -> str | None:
    """读取 VERSION 文件（版本号唯一来源）。"""
    vf = project_path / "VERSION"
    if not vf.is_file():
        return None
    try:
        text = vf.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    m = VERSION_RE.match(text)
    return m.group(1) if m else text.splitlines()[0].strip()


def parse_changelog(project_path: Path, limit: int = 30) -> list[dict]:
    """解析 CHANGELOG.md，返回 [{version, date, groups: [{title, items}]}]。"""
    cf = project_path / "CHANGELOG.md"
    if not cf.is_file():
        return []
    try:
        lines = cf.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict] = []
    current: dict | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        head = CHANGELOG_HEAD_RE.match(line)
        if head:
            if current:
                entries.append(current)
            current = {
                "version": head.group(1).strip(),
                "date": (head.group(2) or "").strip(),
                "groups": [],
            }
            if len(entries) >= limit:
                break
            continue
        group = CHANGELOG_GROUP_RE.match(line)
        if current and group:
            current["groups"].append({"title": group.group(1).strip(), "items": []})
            continue
        if current and current["groups"] and line.startswith(("-", "*", "+")):
            item = line.lstrip("-*+ ").strip()
            if item:
                current["groups"][-1]["items"].append(item)
    if current:
        entries.append(current)
    return entries[:limit]


def list_build_artifacts(project_path: Path, limit_versions: int = 10) -> dict:
    """扫描 versions/vX.Y.Z（含 dist/ 产物）与根 dist/。"""
    result = {"versions": [], "dist": []}
    versions_dir = project_path / "versions"
    if versions_dir.is_dir():
        dirs = sorted(versions_dir.iterdir(), key=lambda p: p.name.lower(), reverse=True)
        for vdir in dirs[:limit_versions]:
            if not vdir.is_dir():
                continue
            entry = {"name": vdir.name, "path": str(vdir), "artifacts": [], "has_src": (vdir / "src").is_dir()}
            dist = vdir / "dist"
            if dist.is_dir():
                for f in sorted(dist.iterdir()):
                    entry["artifacts"].append({
                        "name": f.name,
                        "path": str(f),
                        "size": f.stat().st_size if f.is_file() else None,
                        "kind": "file" if f.is_file() else "dir",
                    })
            result["versions"].append(entry)
    dist_root = project_path / "dist"
    if dist_root.is_dir():
        for f in sorted(dist_root.iterdir()):
            result["dist"].append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size if f.is_file() else None,
            })
    return result


def project_version_summary(project_path: Path, changelog_limit: int = 30) -> dict:
    return {
        "version": read_version(project_path),
        "changelog": parse_changelog(project_path, changelog_limit),
        "artifacts": list_build_artifacts(project_path),
        "has_versions_dir": (project_path / "versions").is_dir(),
        "has_dist_dir": (project_path / "dist").is_dir(),
    }
