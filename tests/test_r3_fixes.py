from __future__ import annotations

import asyncio
import types
from pathlib import Path

import pytest

from projectdock import agent as agent_mod
from projectdock.db import connect, get_project, upsert_project
from projectdock.runner import Job, JobRegistry
from projectdock.scanner import make_folder_name, sanitize_title


def test_upsert_rename_folder(tmp_path):
    """文件夹重命名：同路径换新 id，不应触发 UNIQUE(path) 冲突。"""
    conn = connect(tmp_path / "data.db")
    path = str(tmp_path / "项目1-软件-A")
    upsert_project(conn, "项目1-软件-A", "项目1-软件-A", "软件", path)
    upsert_project(conn, "项目2-软件-A", "项目2-软件-A", "软件", path)
    assert get_project(conn, "项目1-软件-A") is None
    assert get_project(conn, "项目2-软件-A") is not None


def test_upsert_root_change(tmp_path):
    """更换管理根目录：同 id 换新路径，应更新 path 而不是报错。"""
    conn = connect(tmp_path / "data.db")
    upsert_project(conn, "项目1-软件-A", "项目1-软件-A", "软件", str(tmp_path / "old" / "项目1-软件-A"))
    upsert_project(conn, "项目1-软件-A", "项目1-软件-A", "软件", str(tmp_path / "new" / "项目1-软件-A"))
    row = get_project(conn, "项目1-软件-A")
    assert row is not None and row["path"].endswith("项目1-软件-A")
    assert "new" in row["path"]


def test_list_all_after_folder_rename(client):
    """磁盘重命名后 /api/projects 不应 500，且能识别新 id。"""
    created = client.post("/api/projects", json={"name": "改名", "type": "软件", "description": ""}).json()
    root = client.app.state.pd_state.settings.root
    old = root / created["id"]
    new = root / "项目2-软件-改名"
    old.rename(new)
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert "项目2-软件-改名" in ids
    assert "项目1-软件-改名" not in ids


def test_sanitize_title():
    assert "/" not in sanitize_title("a/b\\c:*.?")
    assert ".." not in sanitize_title("..\\..\\evil")
    assert sanitize_title("   ") == "未命名项目"
    assert sanitize_title(" 你好 ") == "你好"


def test_make_folder_name_sanitizes(tmp_path):
    name = make_folder_name(tmp_path, "软件", "a/b: bad")
    assert name.startswith("项目1-软件-")
    assert "/" not in name and ":" not in name


def test_create_project_github_without_preset(client, monkeypatch):
    """勾选 GitHub 但关闭预设：应自动 git init + 首次提交后再建仓。"""
    import projectdock.github as gh_mod

    calls = []
    monkeypatch.setattr(gh_mod, "create_repo",
                        lambda path, name, visibility: calls.append((path, name)) or {"ok": False, "message": "stubbed"})
    resp = client.post("/api/projects", json={
        "name": "GitHub项目", "type": "软件", "description": "", "preset": False, "github": True,
    })
    assert resp.status_code == 201
    created = resp.json()
    project = client.app.state.pd_state.settings.root / created["id"]
    assert (project / ".git").is_dir()
    assert len(calls) == 1
    assert created["github"]["message"] == "stubbed"


def test_agent_start_failure_emits_report(tmp_path, monkeypatch):
    """agent 命令无法启动时也应输出任务报告，并向上抛出异常。"""
    monkeypatch.setitem(agent_mod.AGENTS["pi"], "command", ["no-such-agent-cmd-xyz-123", "-p", "{prompt}"])
    lines: list = []
    state = types.SimpleNamespace(settings=types.SimpleNamespace(backup=False))

    async def run():
        await agent_mod.run_agent_task(state, tmp_path, "pi", "hello", lines.append)

    with pytest.raises(Exception):
        asyncio.run(run())
    # emit 现在支持结构化状态事件（dict）与普通文本（str）
    report = "\n".join(x for x in lines if isinstance(x, str))
    assert any(isinstance(x, dict) and x.get("type") == "status" for x in lines)
    assert "任务报告" in report
    assert "失败" in report


def test_runner_prune():
    reg = JobRegistry()
    reg.MAX_JOBS = 3
    for i in range(5):
        j = Job(id=str(i), label="x", status="done")
        reg._jobs[j.id] = j
    reg._prune()
    assert len(reg._jobs) == 3
    assert sorted(reg._jobs.keys()) == ["2", "3", "4"]



def test_remove_project_stays_hidden(client):
    """移除管理后，文件夹仍存在但不应在列表中重新出现。"""
    created = client.post("/api/projects", json={"name": "待移除", "type": "软件", "description": ""}).json()
    assert created["id"] in [p["id"] for p in client.get("/api/projects").json()]
    resp = client.delete("/api/projects/" + created["id"])
    assert resp.status_code == 200
    ids = [p["id"] for p in client.get("/api/projects").json()]
    assert created["id"] not in ids



def test_root_serves_frontend(client):
    """GET / 应返回前端 HTML 而非“前端目录缺失”回退。"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<title>ProjectDock" in resp.text
    assert "前端目录缺失" not in resp.text



def test_frontend_hidden_rule_present():
    """防回归：hidden 属性必须优先于 display:flex，否则空状态/模态遮罩会拦截交互。"""
    css = Path(__file__).resolve().parents[1] / "web" / "css" / "style.css"
    text = css.read_text(encoding="utf-8")
    assert "[hidden]" in text
    assert "display: none !important" in text
