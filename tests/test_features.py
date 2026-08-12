from __future__ import annotations

from pathlib import Path

from projectdock.scanner import find_documents, find_logo


def _make_project(client, name="Logo项目", ptype="软件"):
    created = client.post("/api/projects", json={"name": name, "type": ptype, "description": ""}).json()
    return created, client.app.state.pd_state.settings.root / created["id"]


def test_find_logo(tmp_path):
    assert find_logo(tmp_path) is None
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.png").write_bytes(b"png")
    assert find_logo(tmp_path) == tmp_path / "assets" / "logo.png"
    (tmp_path / "icon.ico").write_bytes(b"ico")
    assert find_logo(tmp_path) == tmp_path / "icon.ico"


def test_find_documents(tmp_path):
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    (tmp_path / "计划书.md").write_text("计划", encoding="utf-8")
    (tmp_path / "企划书.docx").write_text("x", encoding="utf-8")
    (tmp_path / "main.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "需求文档.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "设计方案.docx").write_text("x", encoding="utf-8")
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions" / "v0.1.0").mkdir()
    (tmp_path / "versions" / "v0.1.0" / "更新计划书.md").write_text("x", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "构建方案.txt").write_text("x", encoding="utf-8")

    docs = find_documents(tmp_path)
    names = [d["name"] for d in docs]
    assert "README.md" in names
    assert "计划书.md" in names
    assert "企划书.docx" in names
    assert "需求文档.pdf" in names
    assert "设计方案.docx" in names
    assert "main.py" not in names
    assert "更新计划书.md" not in names  # versions 被跳过
    assert "构建方案.txt" not in names  # build 被跳过
    # 排序：README 最前，计划书其次
    assert names.index("README.md") < names.index("计划书.md") < names.index("设计方案.docx")


def test_has_logo_and_logo_endpoint(client):
    created, project = _make_project(client)
    pid = created["id"]
    assert client.get(f"/api/projects/{pid}/logo").status_code == 404
    (project / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    assert any(p["has_logo"] for p in client.get("/api/projects").json() if p["id"] == pid)
    resp = client.get(f"/api/projects/{pid}/logo")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")


def test_documents_endpoint(client):
    created, project = _make_project(client, "文档项目")
    pid = created["id"]
    (project / "README.md").write_text("hi", encoding="utf-8")
    (project / "企划书.md").write_text("企划", encoding="utf-8")
    docs = client.get(f"/api/projects/{pid}/documents").json()
    names = [d["name"] for d in docs]
    assert "README.md" in names and "企划书.md" in names
    assert all(d["kind"] for d in docs)


def test_open_file_inside_project(client, monkeypatch):
    created, project = _make_project(client, "打开项目")
    pid = created["id"]
    f = project / "测试.txt"
    f.write_text("x", encoding="utf-8")
    calls = []
    monkeypatch.setattr("projectdock.api.os.startfile", lambda p: calls.append(p))
    resp = client.post(f"/api/projects/{pid}/open-file", json={"path": str(f)})
    assert resp.status_code == 200
    assert calls and Path(calls[0]) == f


def test_open_file_rejects_outside(client):
    created, project = _make_project(client, "越界项目")
    pid = created["id"]
    outside = project.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    resp = client.post(f"/api/projects/{pid}/open-file", json={"path": str(outside)})
    assert resp.status_code == 400
    resp = client.post(f"/api/projects/{pid}/open-file", json={"path": str(project / "不存在.txt")})
    assert resp.status_code == 404


def test_reveal_file(client, monkeypatch):
    created, project = _make_project(client, "定位项目")
    pid = created["id"]
    f = project / "产物.exe"
    f.write_bytes(b"MZ")
    calls = []
    monkeypatch.setattr("projectdock.api.subprocess.Popen", lambda cmd: calls.append(cmd))
    resp = client.post(f"/api/projects/{pid}/reveal-file", json={"path": str(f)})
    assert resp.status_code == 200
    assert calls and calls[0][:2] == ["explorer", "/select,"]
