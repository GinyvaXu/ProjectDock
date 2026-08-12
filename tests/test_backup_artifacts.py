# -*- coding: utf-8 -*-
"""备份管理 + installer/build 产物扫描 + 版本感知归档 + 结构化任务事件。"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from projectdock import backup
from projectdock.compliance import archive_root_artifacts, check_compliance
from projectdock.versioning import list_build_artifacts


def _software_project(client, name):
    created = client.post("/api/projects", json={"name": name, "type": "软件", "description": "", "preset": False}).json()
    root = client.app.state.pd_state.settings.root
    return created["id"], root / created["id"]


# ---------- 备份管理 ----------
def test_backup_list_create_delete(client):
    pid, path = _software_project(client, "备份项目")
    (path / "code.py").write_text("print(1)\n", encoding="utf-8")
    resp = client.post(f"/api/projects/{pid}/backups")
    assert resp.status_code == 201
    name = resp.json()["name"]
    assert name.startswith("pd_backup_") and name.endswith(".zip")
    listed = client.get(f"/api/projects/{pid}/backups").json()
    assert len(listed) == 1 and listed[0]["name"] == name
    assert (path / "versions" / "backups" / name).is_file()
    # 删除
    resp = client.delete(f"/api/projects/{pid}/backups/{name}")
    assert resp.status_code == 200
    assert client.get(f"/api/projects/{pid}/backups").json() == []


def test_backup_restore_overwrites_and_protects_traversal(client):
    pid, path = _software_project(client, "恢复项目")
    (path / "code.py").write_text("v1\n", encoding="utf-8")
    bdir = path / "versions" / "backups"
    bdir.mkdir(parents=True)
    # 手工构造一个含路径穿越的备份
    evil = bdir / "pd_backup_evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("code.py", "v2\n")
        zf.writestr("../evil.txt", "pwn")
    resp = client.post(f"/api/projects/{pid}/backups/restore", json={"name": "pd_backup_evil.zip", "confirm": True})
    assert resp.status_code == 200
    r = resp.json()
    assert r["restored"] == 1
    assert (path / "code.py").read_text(encoding="utf-8") == "v2\n"
    # 穿越文件不应被写出
    assert not (path.parent / "evil.txt").exists()
    # 未确认 → 400
    resp = client.post(f"/api/projects/{pid}/backups/restore", json={"name": "pd_backup_evil.zip", "confirm": False})
    assert resp.status_code == 400
    # 非法文件名 → 400
    resp = client.post(f"/api/projects/{pid}/backups/restore", json={"name": "..\\..\\x.zip", "confirm": True})
    assert resp.status_code == 400


def test_backup_restore_skips_git_versions(client):
    pid, path = _software_project(client, "恢复跳过")
    (path / "code.py").write_text("v1\n", encoding="utf-8")
    (path / ".git").mkdir()
    bdir = path / "versions" / "backups"
    bdir.mkdir(parents=True)
    evil = bdir / "pd_backup_skip.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("code.py", "v2\n")
        zf.writestr(".git/config", "x")
        zf.writestr("versions/v9/dist/x.exe", "x")
    r = client.post(f"/api/projects/{pid}/backups/restore", json={"name": "pd_backup_skip.zip", "confirm": True}).json()
    assert r["restored"] == 1
    assert not (path / ".git" / "config").exists()
    assert not (path / "versions" / "v9" / "dist" / "x.exe").exists()


# ---------- installer / build 产物扫描（GinyVoC 场景） ----------
def test_list_build_artifacts_sees_installer_and_build(tmp_path):
    project = tmp_path / "项目13-软件-GinyVoC"
    (project / "versions" / "v0.4.0" / "installer").mkdir(parents=True)
    (project / "versions" / "v0.4.0" / "dist").mkdir(parents=True)
    (project / "versions" / "v0.4.0" / "installer" / "GinyVoC-Setup-v0.4.0.exe").write_bytes(b"s")
    (project / "versions" / "v0.4.0" / "dist" / "GinyVoC-Debug-v0.4.0.exe").write_bytes(b"d")
    (project / "installer").mkdir()
    (project / "installer" / "GinyVoC-Debug-v0.6.0.exe").write_bytes(b"n")
    (project / "installer" / "README.md").write_text("readme", encoding="utf-8")
    (project / "build").mkdir()
    (project / "build" / "GinyVoC-Setup-v0.4.0.exe").write_bytes(b"b")
    (project / "build" / "debug").mkdir()  # 中间目录应忽略
    arts = list_build_artifacts(project)
    # 版本目录里 installer + dist 都可见
    v0_4 = arts["versions"][0]
    names = [a["name"] for a in v0_4["artifacts"]]
    assert "GinyVoC-Setup-v0.4.0.exe" in names and "GinyVoC-Debug-v0.4.0.exe" in names
    # 根 installer/ 只认二进制；build/ 只认顶层二进制
    unarchived = [a["name"] for a in arts["dist"]]
    assert "GinyVoC-Debug-v0.6.0.exe" in unarchived
    assert "GinyVoC-Setup-v0.4.0.exe" in unarchived
    assert "README.md" not in unarchived
    assert "debug" not in unarchived
    assert arts["root_dist_newer"] is True


# ---------- 版本感知归档 ----------
def test_archive_root_artifacts_version_aware(tmp_path):
    project = tmp_path / "项目13-软件-GinyVoC"
    project.mkdir(parents=True)
    (project / "VERSION").write_text("0.6.0\n", encoding="utf-8")
    (project / "installer").mkdir()
    (project / "installer" / "GinyVoC-Debug-v0.6.0.exe").write_bytes(b"new")
    (project / "installer" / "GinyVoC-Setup-v0.4.0.exe").write_bytes(b"old4")
    (project / "build").mkdir()
    (project / "build" / "GinyVoC-Portable-v0.4.0.exe").write_bytes(b"port4")
    (project / "build" / "win-unpacked").mkdir()
    result = archive_root_artifacts(project)
    assert result["ok"] is True
    assert (project / "versions" / "v0.6.0" / "dist" / "GinyVoC-Debug-v0.6.0.exe").exists()
    assert (project / "versions" / "v0.4.0" / "dist" / "GinyVoC-Setup-v0.4.0.exe").exists()
    assert (project / "versions" / "v0.4.0" / "dist" / "GinyVoC-Portable-v0.4.0.exe").exists()
    assert not (project / "installer" / "GinyVoC-Debug-v0.6.0.exe").exists()
    assert not (project / "build" / "GinyVoC-Portable-v0.4.0.exe").exists()


def test_archive_root_artifacts_skips_identical_duplicate(tmp_path):
    project = tmp_path / "项目14-软件-ProjectDock"
    project.mkdir(parents=True)
    (project / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    (project / "dist").mkdir()
    (project / "dist" / "App.exe").write_bytes(b"MZ")
    (project / "versions" / "v0.4.0" / "dist").mkdir(parents=True)
    (project / "versions" / "v0.4.0" / "dist" / "App.exe").write_bytes(b"MZ")
    result = archive_root_artifacts(project)
    assert result["ok"] is True
    assert (project / "dist" / "App.exe").exists()  # 重复保留，不删除
    assert len(result["skipped"]) == 1


def test_check_compliance_adds_archive_artifacts_action(tmp_path):
    project = tmp_path / "项目13-软件-GinyVoC"
    project.mkdir(parents=True)
    (project / "VERSION").write_text("0.6.0\n", encoding="utf-8")
    (project / "installer").mkdir()
    (project / "installer" / "GinyVoC-Debug-v0.6.0.exe").write_bytes(b"x")
    report = check_compliance(project, "软件")
    keys = [a["key"] for a in report["actions"]]
    assert "archive_artifacts" in keys


# ---------- 结构化任务事件（runner emit dict） ----------
def test_job_registry_emits_structured_events(state):
    import asyncio
    from projectdock.runner import JobRegistry
    reg = JobRegistry()

    async def task(emit):
        emit({"type": "status", "text": "正在思考…"})
        emit("普通输出行")
        emit({"type": "line", "text": "结构化行"})

    job = reg.start_task("测试", task)
    # 等待任务结束
    for _ in range(100):
        if job.status != "running":
            break
        asyncio.run(asyncio.sleep(0.01))
    assert job.status == "done"
    items = []
    while not job.queue.empty():
        items.append(job.queue.get_nowait())
    types = [i.get("type") for i in items]
    assert "status" in types
    line_texts = [i["text"] for i in items if i.get("type") == "line"]
    assert "普通输出行" in line_texts and "结构化行" in line_texts
    assert items[-1]["type"] == "end"
