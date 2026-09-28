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
        text = vf.read_text(encoding="utf-8-sig").strip()
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


def _entry_stat(f: Path, source: str, version: str | None) -> dict:
    try:
        mtime = f.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "name": f.name,
        "path": str(f),
        "size": f.stat().st_size if f.is_file() else None,
        "kind": "file" if f.is_file() else "dir",
        "mtime": mtime,
        "source": source,          # "dist"=根目录未归档 / "versions"=版本目录内
        "version": version,        # versions 内产物所属版本目录名
    }


# 根级可视为「未归档构建产物目录」的子目录（build/ 仅认顶层二进制文件，避免中间目录）
ROOT_ARTIFACT_DIRS = ("dist", "installer", "build")
_BUILD_EXT = {".exe", ".msi", ".msix", ".appx", ".appimage", ".deb", ".rpm",
              ".dmg", ".pkg", ".nupkg", ".whl"}


def _is_build_binary(f: Path) -> bool:
    return f.is_file() and f.suffix.lower() in _BUILD_EXT


def _version_artifact(f: Path) -> bool:
    """versions/*/{dist,installer} 内的可见产物：二进制文件或散装目录（onedir/SetupPackage）。"""
    if f.is_dir():
        return True
    return _is_build_binary(f)


def list_build_artifacts(project_path: Path, limit_versions: int = 10) -> dict:
    """扫描 versions/vX.Y.Z（含 dist/、installer/ 产物）、根 dist/installer/build，并汇总「最新构建」。"""
    result = {"versions": [], "dist": [], "latest": []}
    versions_dir = project_path / "versions"
    latest_version: str | None = None
    if versions_dir.is_dir():
        dirs = sorted(versions_dir.iterdir(), key=lambda p: p.name.lower(), reverse=True)
        for vdir in dirs[:limit_versions]:
            if not vdir.is_dir():
                continue
            if latest_version is None:
                latest_version = vdir.name
            entry = {"name": vdir.name, "path": str(vdir), "artifacts": [], "has_src": (vdir / "src").is_dir()}
            seen_art: set[tuple] = set()
            for sub in ("dist", "installer"):
                subdir = vdir / sub
                if subdir.is_dir():
                    for f in sorted(subdir.iterdir()):
                        if _version_artifact(f):
                            e = _entry_stat(f, "versions", vdir.name)
                            key = (e["name"], e["size"])
                            if key in seen_art:
                                continue
                            seen_art.add(key)
                            entry["artifacts"].append(e)
            result["versions"].append(entry)
    newest_archived_mtime = 0.0
    for v in result["versions"]:
        for f in v["artifacts"]:
            newest_archived_mtime = max(newest_archived_mtime, f["mtime"] or 0.0)
    root_dist_newer = False
    seen_root: set[tuple] = set()
    for sub in ROOT_ARTIFACT_DIRS:
        subdir = project_path / sub
        if not subdir.is_dir():
            continue
        for f in sorted(subdir.iterdir()):
            if f.name.startswith("."):
                continue
            # dist/ 保留原行为（文件+散装目录都列出）；installer/build 只列顶层二进制
            if sub != "dist" and not _is_build_binary(f):
                continue
            e = _entry_stat(f, sub, None)
            key = (e["name"], e["size"])
            if key in seen_root:
                continue
            seen_root.add(key)
            result["dist"].append(e)
            if (e["mtime"] or 0.0) > newest_archived_mtime:
                root_dist_newer = True
    latest = sorted(
        list(result["dist"]) + [a for v in result["versions"] for a in v["artifacts"]],
        key=lambda e: e.get("mtime") or 0.0, reverse=True,
    )[:12]
    result["latest"] = latest
    result["latest_version"] = latest_version
    result["root_dist_newer"] = root_dist_newer
    return result


def project_version_summary(project_path: Path, changelog_limit: int = 30,
                            scheme: str = "semver", build_archive: bool = True) -> dict:
    """版本信息汇总：按版本方案（semver / archive / upstream / none）返回。

    - semver  ：VERSION + CHANGELOG + versions/vX.Y.Z + 根 dist（未归档构建）
    - archive ：archive/ 与 versions/ 子目录 + dist 交付物（不标未归档）
    - upstream：同 semver 读取（只读展示），不标未归档
    - none    ：不追踪版本（返回空结构）
    """
    if scheme == "archive":
        return _archive_summary(project_path)
    if scheme == "none":
        return {
            "version": None,
            "changelog": [],
            "scheme": "none",
            "artifacts": {"versions": [], "dist": [], "latest": [], "latest_version": None},
            "has_versions_dir": (project_path / "versions").is_dir(),
            "has_dist_dir": (project_path / "dist").is_dir(),
            "root_dist_newer": False,
        }
    data = {
        "version": read_version(project_path),
        "changelog": parse_changelog(project_path, changelog_limit),
        "scheme": scheme,
        "artifacts": list_build_artifacts(project_path),
        "has_versions_dir": (project_path / "versions").is_dir(),
        "has_dist_dir": (project_path / "dist").is_dir(),
    }
    if not build_archive:
        data["artifacts"]["root_dist_newer"] = False
    return data


def list_archive_entries(project_path: Path, limit: int = 30) -> list[dict]:
    """归档型版本目录：archive/ 与 versions/ 下的子目录（按 日期+版本 倒序），内含一层产物。"""
    entries: list[dict] = []
    for base_name in ("versions", "archive"):
        base = project_path / base_name
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir(), key=lambda p: _archive_sort_key(p.name), reverse=True)
        except OSError:
            continue
        for d in children[:limit]:
            if not d.is_dir() or d.name.startswith("."):
                continue
            artifacts: list[dict] = []
            try:
                items = sorted(d.iterdir())
            except OSError:
                items = []
            for f in items:
                if f.name.startswith("."):
                    continue
                artifacts.append(_entry_stat(f, "archive", d.name))
            entries.append({"name": d.name, "path": str(d), "artifacts": artifacts,
                            "has_src": (d / "src").is_dir(), "source": base_name})
    return entries


_ARCHIVE_NAME_RE = re.compile(r"^v?([\d.]+)_(\d{8})$")


def _archive_sort_key(name: str) -> tuple:
    """归档目录排序键：`v<版本>_<YYYYMMDD>` 按 日期 → 版本号 自然排序；其它命名靠后按名称。"""
    m = _ARCHIVE_NAME_RE.match(name)
    if m:
        parts = tuple(int(x) for x in m.group(1).split(".") if x)
        return (1, int(m.group(2)), parts, name.lower())
    return (0, 0, (), name.lower())


def _deliverable_items(project_path: Path) -> list[dict]:
    """archive 方案的交付物：根目录 dist/installer/build 下全部可见条目（文件+目录）。"""
    out: list[dict] = []
    seen: set[tuple] = set()
    for sub in ROOT_ARTIFACT_DIRS:
        subdir = project_path / sub
        if not subdir.is_dir():
            continue
        try:
            children = sorted(subdir.iterdir())
        except OSError:
            continue
        for f in children:
            if f.name.startswith("."):
                continue
            e = _entry_stat(f, sub, None)
            key = (e["name"], e["size"])
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
    return out


def _archive_summary(project_path: Path) -> dict:
    entries = list_archive_entries(project_path)
    dist_items = _deliverable_items(project_path)
    latest = sorted(
        [a for e in entries for a in e["artifacts"]] + dist_items,
        key=lambda e: e.get("mtime") or 0.0, reverse=True,
    )[:12]
    return {
        "version": None,
        "changelog": [],
        "scheme": "archive",
        "artifacts": {"versions": entries, "dist": dist_items, "latest": latest,
                      "latest_version": entries[0]["name"] if entries else None},
        "has_versions_dir": (project_path / "versions").is_dir(),
        "has_dist_dir": (project_path / "dist").is_dir(),
        "root_dist_newer": False,
    }
