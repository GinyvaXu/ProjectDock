from __future__ import annotations

import subprocess
import time
import zipfile

from projectdock.agent import system_prompt
from projectdock.backup import make_backup
from projectdock.github import gh_available, repo_name_for


def _wait_done(client, job_id, timeout=40.0):
    status = {"status": "running"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] != "running":
            return status
        time.sleep(0.15)
    return status


def test_custom_type_crud_and_preset(client):
    resp = client.post("/api/types", json={
        "name": "数据分析",
        "label": "数据分析",
        "description": "数据类项目",
        "dirs": ["data", "output"],
        "files": {"README.md": "# {title}\n{description}", "data/说明.txt": "数据目录"},
        "git": True,
    })
    assert resp.status_code == 201
    types = client.get("/api/types").json()
    assert any(t["name"] == "数据分析" and t["custom"] for t in types)
    presets = client.get("/api/presets").json()
    assert any(p["type"] == "数据分析" for p in presets)

    created = client.post("/api/projects", json={"name": "销量分析", "type": "数据分析", "description": "x"}).json()
    assert created["name"] == "项目1-数据分析-销量分析"
    project = client.app.state.pd_state.settings.root / created["name"]
    assert (project / "data").is_dir() and (project / "output").is_dir()
    assert "# 销量分析" in (project / "README.md").read_text(encoding="utf-8")
    assert (project / "data" / "说明.txt").is_file()
    assert created["preset"]["git"] is True

    assert client.delete("/api/types/数据分析").status_code == 200
    assert all(t["name"] != "数据分析" for t in client.get("/api/types").json())


def test_custom_type_rejects_builtin_name(client):
    resp = client.post("/api/types", json={"name": "软件"})
    assert resp.status_code == 400


def test_release_flow(client):
    client.post("/api/projects", json={"name": "发布项目", "type": "软件", "description": ""})
    pid = "项目1-软件-发布项目"
    resp = client.post(f"/api/projects/{pid}/release", json={
        "version": "0.2.0", "changelog": "- 新增发布功能", "build_script": None, "push": False,
    })
    assert resp.status_code == 200
    status = _wait_done(client, resp.json()["job_id"])
    assert status["status"] == "done", status
    project = client.app.state.pd_state.settings.root / pid
    assert (project / "VERSION").read_text(encoding="utf-8").strip() == "0.2.0"
    assert "[0.2.0]" in (project / "CHANGELOG.md").read_text(encoding="utf-8")
    tag = subprocess.run(["git", "tag", "--list", "v0.2.0"], cwd=str(project), capture_output=True, text=True)
    assert "v0.2.0" in tag.stdout
    stream = client.get(f"/api/jobs/{resp.json()['job_id']}/stream")
    assert "发布报告" in stream.text


def test_release_bad_version(client):
    client.post("/api/projects", json={"name": "发布项目", "type": "软件", "description": ""})
    resp = client.post("/api/projects/项目1-软件-发布项目/release", json={"version": "abc", "changelog": ""})
    assert resp.status_code == 400


def test_backup_zip(tmp_path):
    project = tmp_path / "项目1-软件-A"
    project.mkdir()
    (project / "README.md").write_text("hi", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("x", encoding="utf-8")
    (project / "versions").mkdir()
    (project / "versions" / "v1").mkdir()
    (project / "versions" / "v1" / "old.exe").write_bytes(b"x")
    (project / "logs").mkdir()
    (project / "logs" / "a.log").write_text("log", encoding="utf-8")
    target = make_backup(project)
    assert target.exists() and target.suffix == ".zip"
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    assert "README.md" in names
    assert not any("v1/old.exe" in n or ".git" in n or "a.log" in n for n in names)


def test_git_status(client):
    client.post("/api/projects", json={"name": "Git项目", "type": "软件", "description": ""})
    pid = "项目1-软件-Git项目"
    status = client.get(f"/api/projects/{pid}/git-status").json()
    assert status["has_git"] is True
    project = client.app.state.pd_state.settings.root / pid
    (project / "新文件.txt").write_text("x", encoding="utf-8")
    status = client.get(f"/api/projects/{pid}/git-status").json()
    assert status["dirty"] is True
    assert any("新文件.txt" in f for f in status["files"])


def test_agent_type_context():
    info = {"name": "软件", "label": "软件", "dirs": ["src", "tests"], "files": {"README.md": "x", "VERSION": "0.1.0"}, "git": True}
    prompt = system_prompt("项目1-软件-A", "C:/x", info)
    assert "目录结构约定" in prompt and "src" in prompt
    assert "骨架文件约定" in prompt and "README.md" in prompt
    assert "遵循这些结构约定" in prompt


def test_github_repo_name():
    assert repo_name_for("我的 项目") == "我的-项目"
    assert repo_name_for("   ") == "project"
    assert isinstance(gh_available(), bool)


def test_release_with_build(client):
    client.post("/api/projects", json={"name": "构建发布", "type": "软件", "description": ""})
    pid = "项目1-软件-构建发布"
    state = client.app.state.pd_state
    (state.settings.root / pid / "build_debug.py").write_text("print('build ok')", encoding="utf-8")
    resp = client.post(f"/api/projects/{pid}/release", json={
        "version": "0.3.0", "changelog": "", "build_script": "build_debug.py", "push": False,
    })
    status = _wait_done(client, resp.json()["job_id"])
    assert status["status"] == "done", status
    stream = client.get(f"/api/jobs/{resp.json()['job_id']}/stream")
    assert "build ok" in stream.text


def test_release_build_failure(client):
    client.post("/api/projects", json={"name": "构建失败", "type": "软件", "description": ""})
    pid = "项目1-软件-构建失败"
    state = client.app.state.pd_state
    (state.settings.root / pid / "build_debug.py").write_text("import sys; sys.exit(2)", encoding="utf-8")
    resp = client.post(f"/api/projects/{pid}/release", json={
        "version": "0.4.0", "changelog": "", "build_script": "build_debug.py", "push": False,
    })
    status = _wait_done(client, resp.json()["job_id"])
    assert status["status"] == "error", status
    assert "构建失败" in (status.get("error") or "")


def test_github_create_repo_missing(monkeypatch, tmp_path):
    import projectdock.github as gh_mod

    monkeypatch.setattr(gh_mod.shutil, "which", lambda name: None)
    result = gh_mod.create_repo(tmp_path, "demo", "private")
    assert result["ok"] is False
    assert "gh" in result["message"]


def test_resolve_command_windows(monkeypatch):
    import projectdock.agent as agent_mod

    monkeypatch.setattr(agent_mod.shutil, "which", lambda name: r"C:\x\pi.cmd" if name == "pi" else None)
    cmd = agent_mod.resolve_command(["pi", "-p", "hello"])
    assert cmd[:3] == ["cmd", "/c", "pi"]
    assert cmd[-2:] == ["-p", "hello"]

    monkeypatch.setattr(agent_mod.shutil, "which", lambda name: r"C:\x\claude.exe" if name == "claude" else None)
    cmd = agent_mod.resolve_command(["claude", "-p", "hi", "--flag"])
    assert cmd[0] == r"C:\x\claude.exe"
    assert cmd[1:] == ["-p", "hi", "--flag"]

    monkeypatch.setattr(agent_mod.shutil, "which", lambda name: None)
    assert agent_mod.resolve_command(["missing-tool", "x"]) == ["missing-tool", "x"]
