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
