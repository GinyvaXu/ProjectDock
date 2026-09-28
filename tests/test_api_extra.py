from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from projectdock.runner import Job


def test_presets_endpoint(client):
    presets = client.get("/api/presets").json()
    types = [p["type"] for p in presets]
    assert types == ["软件", "网站", "游戏", "PPT", "文稿", "脚本", "其他",
                     "文档加工", "资料系统", "本地应用", "克隆仓库", "工具脚本"]
    software = next(p for p in presets if p["type"] == "软件")
    assert software["git"] is True
    assert "VERSION" in software["files"]
    assert software["version_scheme"] == "semver"
    doc = next(p for p in presets if p["type"] == "文档加工")
    assert doc["version_scheme"] == "none"


def test_agents_endpoint(client):
    agents = client.get("/api/agents").json()
    assert [a["name"] for a in agents] == ["claude", "pi", "api"]


def test_init_endpoint_updates_description(client):
    client.post("/api/projects", json={"name": "初始化", "type": "软件", "description": "旧描述"})
    pid = "项目1-软件-初始化"
    resp = client.post(f"/api/projects/{pid}/init", json={"description": "新描述", "git": True})
    assert resp.status_code == 200
    assert resp.json()["git"] is True
    projects = client.get("/api/projects").json()
    assert projects[0]["description"] == "新描述"


def test_delete_project(client):
    client.post("/api/projects", json={"name": "删除", "type": "脚本"})
    pid = "项目1-脚本-删除"
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    # 文件夹仍在磁盘，但不再出现在管理列表
    assert client.get("/api/projects").json() == []
    assert (client.app.state.pd_state.settings.root / pid).is_dir()
    # 重新导入可恢复管理
    resp = client.post("/api/projects/import", json={
        "path": str(client.app.state.pd_state.settings.root / pid), "type": "脚本"})
    assert resp.status_code == 201
    assert any(p["id"] == pid for p in client.get("/api/projects").json())


def test_open_folder(client, monkeypatch):
    client.post("/api/projects", json={"name": "打开", "type": "其他"})
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p))
    resp = client.post("/api/projects/项目1-其他-打开/open")
    assert resp.status_code == 200
    assert len(opened) == 1 and opened[0].endswith("项目1-其他-打开")


def test_job_not_found(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/stream").status_code == 404


def test_agent_run_endpoint(client, state, monkeypatch):
    client.post("/api/projects", json={"name": "AI", "type": "软件"})
    captured = {}

    def fake_start_task(label, coro_factory):
        captured["label"] = label
        captured["factory"] = coro_factory
        return Job(id="fakejob", label=label)

    monkeypatch.setattr(state.jobs, "start_task", fake_start_task)
    resp = client.post("/api/agent/run", json={
        "project_id": "项目1-软件-AI",
        "prompt": "帮我看看项目结构",
        "agent": "pi",
    })
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "fakejob"
    assert "AI" in captured["label"]


def test_agent_run_with_history(client, state, monkeypatch):
    client.post("/api/projects", json={"name": "AI历史", "type": "软件"})
    captured = {}

    def fake_start_task(label, coro_factory):
        captured["factory"] = coro_factory
        return Job(id="fakejob", label=label)

    monkeypatch.setattr(state.jobs, "start_task", fake_start_task)
    resp = client.post("/api/agent/run", json={
        "project_id": "项目1-软件-AI历史",
        "prompt": "继续整理归档",
        "agent": "pi",
        "history": [
            {"role": "user", "text": "帮我整理版本归档"},
            {"role": "assistant", "text": "好的，已归档到 versions/v1.2.0/dist/。"},
        ],
    })
    assert resp.status_code == 200
    assert captured["factory"]


def test_settings_root_update(client, tmp_path):
    new_root = tmp_path / "newlib"
    new_root.mkdir()
    resp = client.put("/api/settings", json={"root": str(new_root)})
    assert resp.status_code == 200
    assert client.get("/api/projects").json() == []
    assert str(new_root) in (client.get("/api/settings").json()["root"])


def test_settings_persisted(client, state):
    client.put("/api/settings", json={"agent": "pi", "theme": "dark"})
    content = state.settings.path.read_text(encoding="utf-8")
    assert "pi" in content and "dark" in content
