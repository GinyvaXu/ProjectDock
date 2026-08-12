from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

import uvicorn

from .config import APP_NAME, APP_VERSION
from .state import AppState


def _wait_ready(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def run_server(state: AppState, port: int, debug: bool) -> None:
    from .api import create_app

    app = create_app(state)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="debug" if debug else "warning")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="projectdock", description=f"{APP_NAME} v{APP_VERSION}")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-webview", action="store_true", help="只启动后端，不打开窗口")
    parser.add_argument("--debug", action="store_true", help="输出 debug 日志")
    args = parser.parse_args(argv)

    state = AppState.default()
    thread = threading.Thread(target=run_server, args=(state, args.port, args.debug), daemon=True)
    thread.start()
    if not _wait_ready(args.port):
        print("后端启动失败，请检查端口占用", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{args.port}"
    if args.no_webview:
        print(f"{APP_NAME} v{APP_VERSION} 后端已启动：{url} （Ctrl+C 退出）")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    import webview

    webview.create_window(f"{APP_NAME} 项目坞", url, width=1280, height=820, min_size=(1024, 680))
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
