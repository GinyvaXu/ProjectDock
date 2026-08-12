from __future__ import annotations

from pathlib import Path

from projectdock import ailog, console, presets, scanner


def _mk_project(root: Path, name: str, ptype: str = "软件") -> Path:
    proj = root / name
    proj.mkdir()
    return proj


def test_scan_documents_groups_and_skips(tmp_path):
    proj = _mk_project(tmp_path, "项目1-软件-文稿项目")
    (proj / "README.md").write_text("hi", encoding="utf-8")
    (proj / "计划书.md").write_text("计划", encoding="utf-8")
    (proj / "企划书.docx").write_text("x", encoding="utf-8")
    (proj / "需求文档.pdf").write_text("x", encoding="utf-8")
    (proj / "main.py").write_text("print(1)", encoding="utf-8")
    (proj / "docs").mkdir()
    (proj / "docs" / "设计方案.docx").write_text("x", encoding="utf-8")
    for skip in ("versions", "dist", ".venv", "build"):
        d = proj / skip
        d.mkdir()
        (d / ("被跳过-" + skip + ".md")).write_text("x", encoding="utf-8")
        (d / "忽略.docx").write_text("x", encoding="utf-8")

    docs = scanner.scan_documents(proj)
    names = [d["name"] for d in docs]
    assert "README.md" in names and "计划书.md" in names
    assert "企划书.docx" in names and "设计方案.docx" in names
    assert "main.py" not in names
    assert not any("被跳过" in n for n in names)
    assert not any("忽略" in n for n in names)
    # 排序：类型组按固定顺序（Word/PDF/PPT/表格/Markdown/文本），组内按 mtime 倒序
    assert names.index("企划书.docx") < names.index("README.md")
    md = [d for d in docs if d["group"] == "Markdown"]
    assert [d["name"] for d in md] == [d["name"] for d in sorted(md, key=lambda d: -d["mtime"])]
    word = [d for d in docs if d["group"] == "Word 文档"]
    assert [d["name"] for d in word] == [d["name"] for d in sorted(word, key=lambda d: -d["mtime"])]
    assert all(d["group"] for d in docs)


def test_scan_documents_empty(tmp_path):
    assert scanner.scan_documents(tmp_path / "不存在") == []


def test_tabs_for_type_defaults_and_override():
    software = presets.tabs_for_type("软件")
    assert software == ["overview", "github", "versions", "compliance", "ai", "ailog"]
    assert "docs" not in software
    doc = presets.tabs_for_type("文稿")
    assert doc == ["overview", "docs", "ai", "ailog"]
    assert "versions" not in doc and "compliance" not in doc
    other = presets.tabs_for_type("不存在类型")
    assert other == presets.tabs_for_type("其他")
    # 自定义覆盖：去掉 compliance，乱序 + 非法 key 被过滤（已含 overview 则不重排）
    override = {"软件": ["ai", "overview", "bogus", "versions"]}
    tabs = presets.tabs_for_type("软件", override)
    assert tabs == ["ai", "overview", "github", "versions", "ailog"]
    # overview / ailog 始终保留
    assert presets.tabs_for_type("文稿", {"文稿": ["ai"]}) == ["overview", "ai", "ailog"]


def test_collect_activity_merges_projects(tmp_path):
    a = _mk_project(tmp_path, "项目1-软件-A")
    b = _mk_project(tmp_path, "项目2-文稿-B")
    (tmp_path / "无关文件夹").mkdir()
    p1 = ailog.write_log(a, agent="codex", action="写日志A", result="done", summary="A 完成")
    p2 = ailog.write_log(b, agent="claude", action="写日志B", result="failed", summary="B 失败")
    p3 = ailog.write_log(a, agent="pi", action="写日志A2", result="run", summary="A 运行中")

    activity = console.collect_activity(tmp_path, limit=10)
    assert len(activity) == 3
    actions = {e["action"] for e in activity}
    assert actions == {"写日志A", "写日志B", "写日志A2"}
    by_action = {e["action"]: e for e in activity}
    assert by_action["写日志A"]["project"] == "项目1-软件-A"
    assert by_action["写日志B"]["project"] == "项目2-文稿-B"
    assert all("project_path" in e for e in activity)
    # 时间倒序
    ts = [e["ts"] for e in activity]
    assert ts == sorted(ts, reverse=True)
    # limit 生效
    assert len(console.collect_activity(tmp_path, limit=1)) == 1
    assert p1.exists() and p2.exists() and p3.exists()


def test_collect_activity_skips_non_projects(tmp_path):
    (tmp_path / "普通文件夹").mkdir()
    (tmp_path / "普通文件夹" / "logs").mkdir(parents=True)
    (tmp_path / "普通文件夹" / "logs" / "ai").mkdir(parents=True)
    assert console.collect_activity(tmp_path) == []


def test_jobs_endpoint(client):
    created = client.post("/api/projects", json={"name": "任务项目", "type": "软件"}).json()
    proj = Path(client.app.state.pd_state.settings.root) / created["id"]
    (proj / "build.py").write_text('print("hi")', encoding="utf-8")
    resp = client.post("/api/projects/" + created["id"] + "/build", json={"script": "build.py"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    jobs = client.get("/api/jobs").json()
    assert isinstance(jobs, list)
    assert any(j["id"] == job_id for j in jobs)


def test_console_endpoint(client):
    created = client.post("/api/projects", json={"name": "控制台项目", "type": "软件"}).json()
    proj = Path(client.app.state.pd_state.settings.root) / created["id"]
    ailog.write_log(proj, agent="codex", action="写总控台日志", result="done", summary="完成")

    data = client.get("/api/console").json()
    assert data["activity"] and data["activity"][0]["action"] == "写总控台日志"
    assert data["activity"][0]["project"] == created["id"]
    assert isinstance(data["running_jobs"], list)
    assert isinstance(data["failed_count"], int)
    assert any(p["id"] == created["id"] for p in data["projects"])


def test_agent_batch_endpoint(client, state, monkeypatch):
    import projectdock.api as api_mod
    created = client.post("/api/projects", json={"name": "批量项目", "type": "软件"}).json()
    ran = {}

    async def fake_run_agent_task(st, proj_path, agent, prompt, emit, context=None):
        ran["path"] = str(proj_path)
        ran["agent"] = agent
        ran["prompt"] = prompt
        ran["context"] = context
        emit({"type": "line", "text": "ok"})

    monkeypatch.setattr(api_mod.agent_mod, "run_agent_task", fake_run_agent_task)
    resp = client.post("/api/agent/batch", json={
        "project_ids": [created["id"], "项目99-软件-不存在"],
        "prompt": "统一整理版本",
    })
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 2
    ok = next(j for j in jobs if j["project_id"] == created["id"])
    bad = next(j for j in jobs if j["project_id"] == "项目99-软件-不存在")
    assert ok["job_id"]
    assert bad["error"]
    assert ran["path"].endswith(created["id"])
    assert ran["context"] and "ProjectDock" in ran["context"]
    assert "统一整理版本" in ran["prompt"]


def test_settings_type_tabs_roundtrip(client):
    resp = client.put("/api/settings", json={"type_tabs": {"软件": ["overview", "ai", "ailog"], "文稿": ["overview", "docs", "ai", "ailog"]}})
    assert resp.status_code == 200
    saved = client.get("/api/settings").json()
    assert saved["type_tabs"]["软件"] == ["overview", "ai", "ailog"]
    types = client.get("/api/types").json()
    software = next(t for t in types if t["name"] == "软件")
    assert software["tabs"] == ["overview", "github", "ai", "ailog"]
    doc = next(t for t in types if t["name"] == "文稿")
    assert doc["tabs"] == ["overview", "docs", "ai", "ailog"]


def test_types_endpoint_has_tabs_and_labels(client):
    types = client.get("/api/types").json()
    assert types
    for t in types:
        assert t["tabs"] and t["tabs"][0] == "overview"
        assert set(t["tabs"]) <= set(t["tab_labels"])
        assert t["tabs"][-1] == "ailog"
