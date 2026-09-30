from __future__ import annotations

from projectdock.compliance import check_compliance, detect_build_artifacts, quick_compliance
from projectdock.versioning import list_build_artifacts


def _software_project(client, name="Compliance", preset=False):
    created = client.post("/api/projects", json={"name": name, "type": "软件", "description": "", "preset": preset}).json()
    root = client.app.state.pd_state.settings.root
    return created["id"], root / created["id"]


def test_fresh_preset_software_is_compliant(client):
    pid, path = _software_project(client, "合规新项目", preset=True)
    report = check_compliance(path, "软件")
    assert report["compliant"] is True
    assert report["summary"]["passed"] == report["summary"]["total"]
    assert quick_compliance(path, "软件") is True
    assert client.get("/api/projects").json()[0]["compliant"] is True


def test_empty_software_detects_missing_standard(client):
    pid, path = _software_project(client, "不合规项目")
    report = check_compliance(path, "软件")
    assert report["compliant"] is False
    keys = {a["key"] for a in report["actions"]}
    assert {"create_readme", "create_version", "create_changelog", "create_techstack", "create_gitignore", "git_init", "mkdir_versions"} <= keys
    assert client.get("/api/projects").json()[0]["compliant"] is False


def test_fix_endpoint_creates_standard_files(client):
    pid, path = _software_project(client, "修复项目")
    resp = client.post(f"/api/projects/{pid}/compliance/fix", json={
        "actions": ["create_readme", "create_version", "create_changelog", "create_techstack", "create_gitignore", "mkdir_versions", "git_init"],
        "confirm": False,
    })
    assert resp.status_code == 200
    assert all(r["ok"] for r in resp.json()["results"])
    assert (path / "README.md").is_file()
    assert (path / "VERSION").is_file()
    assert (path / "CHANGELOG.md").is_file()
    assert (path / "TECHSTACK.md").is_file()
    assert (path / ".gitignore").is_file()
    assert (path / "versions").is_dir()
    assert check_compliance(path, "软件")["compliant"] is True
    assert client.get("/api/projects").json()[0]["compliant"] is True


def test_archive_dist_requires_confirm_and_moves(client):
    pid, path = _software_project(client, "归档项目")
    dist = path / "dist"
    dist.mkdir()
    (dist / "App.exe").write_bytes(b"MZ")
    (dist / "App_debug.exe").write_bytes(b"MZ")
    # 未确认 → 400
    resp = client.post(f"/api/projects/{pid}/compliance/fix", json={"actions": ["archive_dist"], "confirm": False})
    assert resp.status_code == 400
    assert (dist / "App.exe").exists()
    # 确认后 → 移动归档
    resp = client.post(f"/api/projects/{pid}/compliance/fix", json={"actions": ["archive_dist"], "confirm": True})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["ok"] is True
    assert not (dist / "App.exe").exists()
    assert (path / "versions" / "v0.1.0" / "dist" / "App.exe").exists()
    assert (path / "versions" / "v0.1.0" / "dist" / "App_debug.exe").exists()


def test_unknown_action_rejected(client):
    pid, _ = _software_project(client, "未知动作")
    resp = client.post(f"/api/projects/{pid}/compliance/fix", json={"actions": ["nope"], "confirm": False})
    assert resp.status_code == 400


def test_detect_build_artifacts_filters_junk(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "App.exe").write_bytes(b"MZ")
    (dist / "App_debug.exe").write_bytes(b"MZ")
    (dist / "SetupPackage").mkdir()
    (dist / "report.pdf").write_bytes(b"%PDF")
    (dist / "data123.zip").write_bytes(b"PK")
    (dist / ".build_version").write_text("1.0", encoding="utf-8")
    names = [c.name for c in detect_build_artifacts(dist)]
    assert names == ["App.exe", "App_debug.exe", "SetupPackage"]


def test_latest_build_artifacts_merges_root_dist_and_versions(tmp_path):
    project = tmp_path / "项目1-软件-最新版"
    (project / "versions" / "v1.0.0" / "dist").mkdir(parents=True)
    (project / "versions" / "v1.0.0" / "dist" / "old.exe").write_bytes(b"old")
    (project / "dist").mkdir()
    (project / "dist" / "new.exe").write_bytes(b"new")
    arts = list_build_artifacts(project)
    assert arts["latest_version"] == "v1.0.0"
    latest = arts["latest"]
    assert latest[0]["name"] == "new.exe"
    assert latest[0]["source"] == "dist"
    assert latest[1]["name"] == "old.exe"
    assert latest[1]["source"] == "versions"
    assert latest[1]["version"] == "v1.0.0"
