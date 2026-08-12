"""ProjectDock 启动入口：python run.py"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# PyInstaller windowed 模式下 stdout/stderr 为 None，先重定向到 devnull 防止日志写入崩溃
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _log_crash() -> None:
    try:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ProjectDock"
        base.mkdir(parents=True, exist_ok=True)
        with open(base / "crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().isoformat()} =====\n")
            traceback.print_exc(file=f)
            f.write("\n")
    except Exception:
        pass


from projectdock.main import main  # noqa: E402

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        _log_crash()
        raise
