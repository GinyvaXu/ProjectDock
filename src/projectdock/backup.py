from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {".git", "versions", "dist", "build", ".venv", "venv", "__pycache__", "node_modules", "logs", ".idea", ".vscode", "installer"}


def make_backup(project_path: Path) -> Path:
    """把项目打包成 zip 快照到 versions/backups/（本地保留，git 忽略）。"""
    project_path = Path(project_path)
    backups_dir = project_path / "versions" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backups_dir / f"pd_backup_{ts}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(project_path):
            rel_dir = Path(dirpath).relative_to(project_path)
            # 剪枝：跳过 .git/versions/.venv 等大目录，不深入遍历
            if rel_dir.parts and rel_dir.parts[0] in SKIP_DIRS:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if (rel_dir / d).parts[0] not in SKIP_DIRS]
            for name in filenames:
                file = Path(dirpath) / name
                if file.suffix == ".pyc":
                    continue
                zf.write(file, arcname=str(file.relative_to(project_path)))
                count += 1
    if count == 0:
        target.unlink(missing_ok=True)
        raise ValueError("项目为空，跳过备份")
    return target


def backups_dir(project_path: Path) -> Path:
    return Path(project_path) / "versions" / "backups"


def list_backups(project_path: Path) -> list[dict]:
    """列出 versions/backups/ 下的备份快照（按时间倒序）。"""
    d = backups_dir(project_path)
    out = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("pd_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            st = f.stat()
            out.append({"name": f.name, "path": str(f), "size": st.st_size, "mtime": st.st_mtime})
        except OSError:
            continue
    return out


def delete_backup(project_path: Path, name: str) -> bool:
    """删除指定备份快照（仅允许 versions/backups/ 内的 pd_backup_*.zip）。"""
    d = backups_dir(project_path).resolve()
    target = (d / name).resolve()
    if not name.startswith("pd_backup_") or not name.endswith(".zip"):
        raise ValueError("非法备份文件名")
    try:
        target.relative_to(d)
    except ValueError:
        raise ValueError("备份文件不在备份目录内")
    if not target.is_file():
        return False
    target.unlink()
    return True


def _restore_one(project_path: Path, name: str, auto_backup: bool = True) -> dict:
    """把备份 zip 安全解压回项目（防路径穿越；跳过 .git/versions 等顶层目录）。"""
    project = Path(project_path).resolve()
    d = backups_dir(project)
    target = (d / name).resolve()
    if not name.startswith("pd_backup_") or not name.endswith(".zip"):
        raise ValueError("非法备份文件名")
    try:
        target.relative_to(d)
    except ValueError:
        raise ValueError("备份文件不在备份目录内")
    if not target.is_file():
        raise ValueError("备份文件不存在")
    if auto_backup:
        make_backup(project)  # 恢复前再留一个安全快照
    restored, skipped = [], []
    with zipfile.ZipFile(target, "r") as zf:
        for info in zf.infolist():
            arc = info.filename
            if arc.endswith("/"):
                continue
            clean = arc.replace("\\", "/")
            raw_parts = clean.split("/")
            if ".." in raw_parts:
                skipped.append(clean)
                continue
            parts = [p for p in raw_parts if p not in ("", ".")]
            if not parts:
                continue
            if parts[0] in SKIP_DIRS:
                skipped.append(clean)
                continue
            dest = project.joinpath(*parts)
            try:
                dest.resolve().relative_to(project)
            except ValueError:
                skipped.append(clean)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out_f:
                out_f.write(src.read())
            restored.append(clean)
    return {"restored": len(restored), "skipped": skipped}


def restore_backup(project_path: Path, name: str) -> dict:
    """恢复备份（入口，返回统计）。"""
    return _restore_one(Path(project_path), name)
