from __future__ import annotations

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
        for file in sorted(project_path.rglob("*")):
            if file.is_dir() or file.suffix in (".pyc",):
                continue
            rel = file.relative_to(project_path)
            if rel.parts and rel.parts[0] in SKIP_DIRS:
                continue
            zf.write(file, arcname=str(rel))
            count += 1
    if count == 0:
        target.unlink(missing_ok=True)
        raise ValueError("项目为空，跳过备份")
    return target
