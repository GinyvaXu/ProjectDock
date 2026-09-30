"""v1.1 新功能测试：GitHub 仓库管理 / 项目信息编辑 / Tab 合并 / 总控台标签。"""
from __future__ import annotations

from projectdock import ghrepo
from projectdock.db import get_project


def _create_soft(client, name="测试项目"):
    return client.post("/api/projects", json={"name": name, "type": "软件", "preset": False}).json()


def test_project_update_rename_type_description(client):
    """编辑项目：改名 + 改类型 → 文件夹重命名、旧 id 移除、新 id 可见、置顶保留。"""
    created = _create_soft(client, "旧名字")
    pid = created["id"]
    # 置顶再编辑
    client.post(f"/api/projects/{pid}/pin")
    root = client.app.state.pd_state.settings.root
    assert (root / pid).is_dir()

    r = client.put(f"/api/projects/{pid}", json={"name": "新名字", "type": "网站", "description": "新描述"})
    assert r.status_code == 200
    data = r.json()
    new_id = data["id"]
    assert data["type"] == "网站"
    assert data["title"] == "新名字"
    assert data["description"] == "新描述"
    assert data["pinned"] is True
    assert not (root / pid).exists()
    assert (root / new_id).is_dir()

    ids = [p["id"] for p in client.get("/api/projects").json()]
    assert pid not in ids
    assert new_id in ids


def test_project_update_description_only_no_rename(client):
    """仅编辑描述：不重命名文件夹。"""
    created = _create_soft(client, "仅描述")
    pid = created["id"]
    root = client.app.state.pd_state.settings.root
    r = client.put(f"/api/projects/{pid}", json={"description": "仅描述更新"})
    assert r.status_code == 200
    assert r.json()["id"] == pid
    assert (root / pid).is_dir()
    row = get_project(client.app.state.pd_state.conn, pid)
    assert row["description"] == "仅描述更新"


def test_github_auth_login_valid_and_invalid(client, monkeypatch):
    monkeypatch.setattr(ghrepo, "gh_user", lambda token: {"login": "tester", "name": "T"} if token == "ok" else None)
    # 无效令牌 400
    r = client.post("/api/github/auth", json={"token": "bad"})
    assert r.status_code == 400
    # 有效令牌 200 并保存
    r = client.post("/api/github/auth", json={"token": "ok"})
    assert r.status_code == 200
    assert r.json()["user"]["login"] == "tester"
    assert client.app.state.pd_state.settings.github_token == "ok"
    # 退出
    assert client.delete("/api/github/auth").status_code == 200
    assert client.app.state.pd_state.settings.github_token == ""


def test_github_status_endpoint(client, monkeypatch):
    monkeypatch.setattr(ghrepo, "resolve_token", lambda settings: "tok")
    monkeypatch.setattr(ghrepo, "gh_user", lambda token: {"login": "tester", "name": "T", "avatar_url": ""})
    monkeypatch.setattr(ghrepo, "remote_of", lambda p: "https://github.com/owner/repo.git")
    monkeypatch.setattr(ghrepo, "repo_info", lambda token, o, r: {"full_name": "owner/repo", "html_url": "https://github.com/owner/repo", "default_branch": "main", "private": True, "language": "Python", "pushed_at": "2026-08-12T00:00:00Z", "stargazers": 0, "forks": 0, "issues": 0})

    created = _create_soft(client, "gh项目")
    r = client.get(f"/api/projects/{created['id']}/github")
    assert r.status_code == 200
    data = r.json()
    assert data["auth"]["logged_in"] is True
    assert data["remote"]["url"].endswith("repo.git")
    assert data["repo"]["full_name"] == "owner/repo"


def test_github_readme_requires_login(client, monkeypatch):
    monkeypatch.setattr(ghrepo, "resolve_token", lambda settings: "")
    monkeypatch.setattr(ghrepo, "repo_slug", lambda p: ("owner", "repo"))
    created = _create_soft(client, "readme项目")
    r = client.get(f"/api/projects/{created['id']}/github/readme")
    assert r.status_code == 400


def test_github_readme_returns_text(client, monkeypatch):
    monkeypatch.setattr(ghrepo, "resolve_token", lambda settings: "tok")
    monkeypatch.setattr(ghrepo, "repo_slug", lambda p: ("owner", "repo"))
    monkeypatch.setattr(ghrepo, "repo_info", lambda token, o, r: {"default_branch": "main"})
    monkeypatch.setattr(ghrepo, "repo_readme", lambda token, o, r: "# Hello\n\nBody")
    created = _create_soft(client, "readme2")
    r = client.get(f"/api/projects/{created['id']}/github/readme")
    assert r.status_code == 200
    assert "Body" in r.json()["text"]
    assert r.json()["branch"] == "main"


def test_github_create_and_set_remote(client, monkeypatch):
    monkeypatch.setattr(ghrepo, "resolve_token", lambda settings: "tok")
    monkeypatch.setattr(ghrepo, "create_repo", lambda path, name, vis, token="", description="": {"ok": True, "message": "created"})
    created = _create_soft(client, "remote项目")
    pid = created["id"]
    # create
    r = client.post(f"/api/projects/{pid}/github/create", json={"visibility": "private"})
    assert r.status_code == 200 and r.json()["ok"] is True
    # set-remote 需要真实 git（本地环境有 git）
    r = client.post(f"/api/projects/{pid}/github/set-remote", json={"url": "https://github.com/owner/repo.git"})
    assert r.status_code == 200
    # 再次设置同地址仍 200
    r = client.post(f"/api/projects/{pid}/github/set-remote", json={"url": "https://github.com/owner/repo.git"})
    assert r.status_code == 200


def test_software_tabs_include_github(client):
    """已保存 type_tabs 模板也应自动并入新默认 github Tab。"""
    client.app.state.pd_state.settings.update(type_tabs={"软件": ["overview", "versions", "compliance", "ai", "ailog"]})
    types = client.get("/api/types").json()
    soft = next(t for t in types if t["name"] == "软件")
    assert "github" in soft["tabs"]
    # 文稿类不强制加入
    doc = next(t for t in types if t["name"] == "文稿")
    assert "github" not in doc["tabs"]


def test_console_activity_has_project_title(client):
    created = _create_soft(client, "日志项目")
    pid = created["id"]
    client.post(f"/api/projects/{pid}/ai-logs", json={"agent": "codex", "action": "测试动作", "result": "done", "summary": "摘要内容", "details": "详细内容"})
    data = client.get("/api/console").json()
    assert any(e.get("project_title") == "日志项目" for e in data["activity"])
