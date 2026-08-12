"""自动更新：检查 GitHub Releases -> 下载 Setup 安装包 -> 启动安装。

链路：本应用以 Setup 安装包发布到 GitHub Releases（私有仓库，用 gh CLI 鉴权）；
检查更新时读取最新 Release 的 tag/说明，发现新版本后下载 `*Setup*.exe`，
静默运行安装程序（Inno Setup `/VERYSILENT`，安装过程自动关闭正在运行的应用）。
"""
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SETUP_PATTERN = "*Setup*.exe"
DEFAULT_TIMEOUT = 60


def version_tuple(v: str) -> tuple:
    """把 semver 字符串转成可比较元组（0.10.0 > 0.9.9）。"""
    parts = re.split(r"[.-]", str(v or "").strip().lstrip("v"))
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return tuple(nums)


def _gh(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=0x08000000 if os.name == "nt" else 0)


def _api_latest(repo: str, token: str = "") -> dict | None:
    """GET /releases/latest（私有仓库带 gh 令牌），返回 JSON dict 或 None。"""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ProjectDock"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def latest_release(repo: str) -> dict | None:
    """返回最新 Release 的 {tag, notes, published_at, url}；获取失败返回 None。"""
    if repo:
        if shutil.which("gh"):
            try:
                # gh release view 不带 tag 参数时默认展示最新 Release
                r = _gh(["release", "view", "--repo", repo,
                         "--json", "tagName,body,publishedAt,url"])
                if r.returncode == 0 and r.stdout.strip():
                    data = json.loads(r.stdout)
                    return {
                        "tag": data.get("tagName") or "",
                        "notes": data.get("body") or "",
                        "published_at": data.get("publishedAt") or "",
                        "url": data.get("url") or "",
                    }
            except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
                pass
        # 兜底：GitHub API（私有仓库用 gh 令牌鉴权）
        token = ""
        if shutil.which("gh"):
            try:
                t = _gh(["auth", "token"])
                if t.returncode == 0:
                    token = t.stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                pass
        data = _api_latest(repo, token)
        if data:
            return {
                "tag": data.get("tag_name") or "",
                "notes": data.get("body") or "",
                "published_at": data.get("published_at") or "",
                "url": data.get("html_url") or "",
            }
    return None


def check_update(current: str, repo: str) -> dict:
    """对比当前版本与最新 Release，返回检查结果。"""
    rel = latest_release(repo)
    base = {"current": current or "", "repo": repo or ""}
    if not rel:
        return {**base, "status": "unknown", "latest": None, "update_available": False,
                "notes": "", "published_at": "", "url": ""}
    latest = version_tuple(rel["tag"])
    latest_str = str(rel["tag"]).strip().lstrip("v")
    if not latest:
        return {**base, "status": "unknown", "latest": rel["tag"], "update_available": False,
                "notes": rel["notes"], "published_at": rel["published_at"], "url": rel["url"]}
    return {
        **base, "status": "ok", "latest": latest_str,
        "update_available": latest > version_tuple(current),
        "notes": rel["notes"], "published_at": rel["published_at"], "url": rel["url"],
    }


def download_setup(repo: str, tag: str, dest_dir: Path) -> dict:
    """下载最新 Setup 安装包到 dest_dir，返回 {ok, path, size, error}。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        r = _gh(["release", "download", tag, "--repo", repo,
                 "--pattern", SETUP_PATTERN, "--dir", str(dest_dir)], timeout=300)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "path": "", "size": 0, "error": str(exc)}
    if r.returncode != 0:
        return {"ok": False, "path": "", "size": 0,
                "error": (r.stderr or r.stdout or "gh release download 失败").strip()}
    files = sorted(dest_dir.glob(SETUP_PATTERN))
    if not files:
        return {"ok": False, "path": "", "size": 0, "error": "未找到 Setup 安装包"}
    path = files[-1]
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {"ok": True, "path": str(path), "size": size, "error": ""}


def install_setup(setup_path: str) -> dict:
    """静默运行安装程序（Inno Setup）。安装过程会自动关闭正在运行的应用。"""
    path = Path(setup_path)
    if not path.is_file() or path.suffix.lower() != ".exe":
        return {"ok": False, "error": "安装包不存在"}
    cmd = [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
    creationflags = 0x08000000  # CREATE_NO_WINDOW
    try:
        subprocess.Popen(cmd, cwd=str(path.parent), creationflags=creationflags)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "error": ""}


def update_temp_dir() -> Path:
    return Path(tempfile.gettempdir()) / "ProjectDock_update"
