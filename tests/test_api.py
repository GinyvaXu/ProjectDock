from __future__ import annotations

import time

from projectdock.agent import build_command, system_prompt


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["app"] == "ProjectDock"


def test_settings_roundtrip(client):
    resp = client.put("/api/settings", json={"agent": "pi", "theme": "dark"})
    assert resp.status_code == 200
    body = client.get("/api/settings").json()
    assert body["agent"] == "pi"
    assert body["theme"] == "dark"


def test_settings_rejects_unknown_theme(client):
    resp = client.put("/api/settings", json={"theme": "neon"})
    assert resp.status_code == 400


def test_create_project_with_preset(client):
    resp = client.post("/api/projects", json={"name": "演示项目", "type": "软件", "description": "测试"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "项目1-软件-演示项目"
    assert body["version"] == "0.1.0"
    assert body["preset"]["git"] is True
    projects = client.get("/api/projects").json()
    assert len(projects) == 1
    assert projects[0]["has_git"] is True


def test_create_project_without_preset(client):
    resp = client.post("/api/projects", json={"name": "裸项目", "type": "网站", "preset": False})
    assert resp.status_code == 201
    projects = client.get("/api/projects").json()
    assert projects[0]["type"] == "网站"
    assert projects[0]["has_git"] is False


def test_import_project(client, state):
    folder = state.settings.root / "参考资料"
    folder.mkdir()
    resp = client.post("/api/projects/import", json={"path": str(folder), "type": "其他", "description": "资料"})
    assert resp.status_code == 201
    assert resp.json()["imported"] is True
    projects = client.get("/api/projects").json()
    assert any(p["name"] == "参考资料" for p in projects)


def test_import_missing_path(client):
    resp = client.post("/api/projects/import", json={"path": "Z:/不存在的路径", "type": "其他"})
    assert resp.status_code == 400


def test_versions_endpoint(client):
    client.post("/api/projects", json={"name": "版本项目", "type": "软件", "description": ""})
    resp = client.get("/api/projects/项目1-软件-版本项目/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "0.1.0"
    assert len(body["changelog"]) == 1


def test_build_run_and_stream(client):
    client.post("/api/projects", json={"name": "构建项目", "type": "软件", "description": ""})
    pid = "项目1-软件-构建项目"
    state = client.app.state.pd_state
    script_path = state.settings.root / pid / "build_debug.py"
    script_path.write_text("print('hello build')\n", encoding="utf-8")
    builds = client.get(f"/api/projects/{pid}/builds").json()
    assert builds[0]["name"] == "build_debug.py"
    resp = client.post(f"/api/projects/{pid}/build", json={"script": "build_debug.py"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    status = {"status": "running"}
    for _ in range(50):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.1)
    assert status["status"] == "done"
    stream = client.get(f"/api/jobs/{job_id}/stream")
    assert "hello build" in stream.text


def test_unknown_build_script(client):
    client.post("/api/projects", json={"name": "构建项目", "type": "软件", "description": ""})
    resp = client.post("/api/projects/项目1-软件-构建项目/build", json={"script": "nope.py"})
    assert resp.status_code == 404


def test_missing_project_404(client):
    assert client.get("/api/projects/不存在/versions").status_code == 404


def test_agent_command_and_prompt():
    cmd = build_command("claude", "帮我整理目录")
    assert cmd == ["claude", "-p", "帮我整理目录", "--dangerously-skip-permissions"]
    pi_cmd = build_command("pi", "帮我整理目录")
    assert pi_cmd == ["pi", "-p", "帮我整理目录"]
    prompt = system_prompt("项目1-软件-A", "C:/x")
    assert "项目1-软件-A" in prompt
