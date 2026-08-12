"""PyInstaller debug（console）构建 -> versions/vX.Y.Z/dist/。"""

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
        "--console",
        "--name", f"ProjectDock_debug_v{version}",
        "--distpath", str(out),
        "--workpath", str(ROOT / "build" / "debug"),
        "--specpath", str(ROOT / "build"),
        "--add-data", f"{WEB};web",
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--hidden-import", "pydantic",
        str(ENTRY),
    ]
    print("[build_debug] 开始构建 debug 版 v" + version)
    subprocess.check_call(cmd)
    print(f"[build_debug] 完成 -> {out}")


if __name__ == "__main__":
    main()
