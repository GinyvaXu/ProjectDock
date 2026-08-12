"""PyInstaller release（windowed）构建 -> versions/vX.Y.Z/dist/。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from build_utils import current_version, prepare_dist, archive_old_exes

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
ENTRY = ROOT / "run.py"


def main() -> None:
    version = current_version()
    archive_old_exes()
    out = prepare_dist()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", f"ProjectDock_v{version}",
        "--distpath", str(out),
        "--workpath", str(ROOT / "build" / "release"),
        "--specpath", str(ROOT / "build"),
        "--add-data", f"{WEB};web",
        "--paths", str(ROOT / "src"),
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--hidden-import", "pydantic",
        str(ENTRY),
    ]
    print("[build_exe] 开始构建 release 版 v" + version)
    subprocess.check_call(cmd)
    print(f"[build_exe] 完成 -> {out}")


if __name__ == "__main__":
    main()
