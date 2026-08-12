"""GitHub 远程仓库管理：令牌解析 + REST API 读取仓库/README/提交/Release + 建仓推送。

令牌来源优先级：设置中保存的 PAT > gh CLI 登录态。所有写操作尽量复用 gh CLI；
无 gh 时建仓/推送走 REST + git -c http.extraheader 注入令牌（不落盘）。
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"
UA = "ProjectDock/1.0"


class GhError(Exception):
    """GitHub 请求失败（含状态码与信息）。"""


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=0x08000000 if os.name == "nt" else 0)


def _ensure_git(project_path: Path) -> bool:
    """确保项目是 git 仓库（缺失时 git init），返回是否可用。"""
    if (project_path / ".git").is_dir():
        return True
    r = _run(["git", "init"], cwd=str(project_path), timeout=30)
    return r.returncode == 0


def gh_available() -> bool:
    return shutil.which("gh") is not None


def resolve_token(settings) -> str:
    """优先 settings.github_token，其次 gh auth token。"""
    tok = str(getattr(settings, "github_token", "") or "").strip()
    if tok:
        return tok
    if gh_available():
        r = _run(["gh", "auth", "token"])
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return ""


def _request(method: str, path: str, token: str = "", body: dict | None = None) -> dict | list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("message", "")
        except Exception:
            pass
        raise GhError(f"GitHub API {exc.code}: {detail or exc.reason}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise GhError(f"无法连接 GitHub：{exc}") from exc


def gh_user(token: str) -> dict | None:
    """GET /user，未登录/令牌失效返回 None。"""
    if not token:
        return None
    try:
        data = _request("GET", "/user", token)
        if isinstance(data, dict) and data.get("login"):
            return {"login": data["login"], "name": data.get("name") or data["login"],
                    "avatar_url": data.get("avatar_url", "")}
    except GhError:
        return None
    return None


def parse_remote_url(url: str) -> tuple[str, str] | None:
    """解析 git remote 为 (owner, repo)；无法解析返回 None。"""
    s = (url or "").strip().rstrip("/")
    if not s:
        return None
    if s.startswith("git@") and ":" in s:
        s = "https://github.com/" + s.split(":", 1)[1]
    s = re.sub(r"\.git$", "", s)
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+)", s)
    if m:
        return m.group(1), m.group(2)
    return None


def remote_of(project_path: Path) -> str | None:
    """读取 origin 远程地址。"""
    if not (project_path / ".git").is_dir():
        return None
    r = _run(["git", "remote", "get-url", "origin"], cwd=str(project_path), timeout=15)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_slug(project_path: Path) -> tuple[str, str] | None:
    url = remote_of(project_path)
    return parse_remote_url(url) if url else None


def repo_info(token: str, owner: str, repo: str) -> dict:
    data = _request("GET", f"/repos/{owner}/{repo}", token)
    if not isinstance(data, dict):
        raise GhError("仓库信息格式异常")
    return {
        "full_name": data.get("full_name", f"{owner}/{repo}"),
        "html_url": data.get("html_url", ""),
        "description": data.get("description") or "",
        "default_branch": data.get("default_branch", "main"),
        "private": bool(data.get("private")),
        "language": data.get("language") or "",
        "pushed_at": data.get("pushed_at", ""),
        "updated_at": data.get("updated_at", ""),
        "created_at": data.get("created_at", ""),
        "stargazers": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "issues": data.get("open_issues_count", 0),
        "size_kb": data.get("size", 0),
    }


def repo_readme(token: str, owner: str, repo: str) -> str:
    """读取仓库 README（自动探测大小写），返回 markdown 文本。"""
    data = _request("GET", f"/repos/{owner}/{repo}/readme", token)
    if not isinstance(data, dict):
        raise GhError("README 数据异常")
    if data.get("encoding") == "base64" and data.get("content"):
        return base64.b64decode(data["content"]).decode("utf-8", "replace")
    return data.get("content", "")


def repo_commits(token: str, owner: str, repo: str, branch: str | None = None, limit: int = 10) -> list[dict]:
    path = f"/repos/{owner}/{repo}/commits?per_page={max(1, min(limit, 50))}"
    if branch:
        path += "&sha=" + urllib.parse.quote(branch)
    data = _request("GET", path, token)
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        cm = c.get("commit", {})
        author = cm.get("author") or {}
        out.append({
            "sha": (c.get("sha") or "")[:10],
            "message": (cm.get("message") or "").splitlines()[0][:120],
            "date": author.get("date", ""),
            "author": (author.get("name") or ""),
            "html_url": c.get("html_url", ""),
        })
    return out


def repo_releases(token: str, owner: str, repo: str, limit: int = 8) -> list[dict]:
    data = _request("GET", f"/repos/{owner}/{repo}/releases?per_page={max(1, min(limit, 30))}", token)
    if not isinstance(data, list):
        return []
    return [{
        "tag": r.get("tag_name", ""),
        "name": r.get("name") or r.get("tag_name", ""),
        "published_at": r.get("published_at", ""),
        "html_url": r.get("html_url", ""),
        "prerelease": bool(r.get("prerelease")),
        "draft": bool(r.get("draft")),
    } for r in data if not r.get("draft")]


def create_repo(project_path: Path, name: str, visibility: str = "private",
                token: str = "", description: str = "") -> dict:
    """创建远程仓库并推送。优先 gh CLI；无 gh 时走 REST + http.extraheader。"""
    if not (project_path / ".git").is_dir():
        return {"ok": False, "message": "项目尚未初始化 git"}
    from . import github as gh_mod
    if gh_mod.gh_available():
        return gh_mod.create_repo(project_path, name, visibility)
    if not token:
        return {"ok": False, "message": "未检测到 GitHub 登录，请先在设置中登录"}
    try:
        data = _request("POST", "/user/repos", token,
                        body={"name": name, "private": visibility != "public", "description": description})
        if not isinstance(data, dict) or not data.get("clone_url"):
            raise GhError("创建仓库返回异常")
        url = data["clone_url"]
        _run(["git", "remote", "add", "origin", url], cwd=str(project_path), timeout=15)
        r = _run(["git", "-c", f"http.extraheader=Authorization: Bearer {token}", "push", "-u", "origin", "HEAD"],
                 cwd=str(project_path), timeout=180)
        if r.returncode != 0:
            return {"ok": False, "message": (r.stderr or r.stdout).strip() or "推送失败"}
        return {"ok": True, "message": f"已创建并推送 {data.get('full_name', name)}"}
    except GhError as exc:
        return {"ok": False, "message": str(exc)}


def set_remote(project_path: Path, url: str) -> dict:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "message": "远程地址不能为空"}
    if not _ensure_git(project_path):
        return {"ok": False, "message": "git init 失败"}
    existing = remote_of(project_path)
    if existing:
        r = _run(["git", "remote", "set-url", "origin", url], cwd=str(project_path), timeout=15)
    else:
        r = _run(["git", "remote", "add", "origin", url], cwd=str(project_path), timeout=15)
    if r.returncode != 0:
        return {"ok": False, "message": (r.stderr or r.stdout).strip() or "设置远程地址失败"}
    return {"ok": True, "message": f"origin → {url}"}
