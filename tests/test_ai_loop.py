from __future__ import annotations

from projectdock import cli


def _make_project(client, name="日志项目", preset=True):
    client.post("/api/projects", json={"name": name, "type": "软件", "description": "", "preset": preset})
    root = client.app.state.pd_state.settings.root
    return "项目1-软件-" + name, root


def test_ai_logs_api(client):
    pid, root = _make_project(client)
    r = client.post(f"/api/projects/{pid}/ai-logs", json={
        "agent": "codex", "action": "实现总控台", "result": "done", "summary": "完成", "source": "external"})
    assert r.status_code == 201
    assert r.json()["ok"] is True
    logs = client.get(f"/api/projects/{pid}/ai-logs").json()
    assert len(logs) == 1
    assert logs[0]["agent"] == "codex"
    assert logs[0]["action"] == "实现总控台"
    assert (root / pid / "logs" / "ai").is_dir()


def test_contract_api(client):
    pid, root = _make_project(client, name="契约API")
    r = client.post(f"/api/projects/{pid}/contract", json={})
    assert r.status_code == 201
    agen = (root / pid / "AGENTS.md").read_text(encoding="utf-8")
    assert "AI 操作日志" in agen
    # 合规修复动作里出现 create_contract
    rep = client.get(f"/api/projects/{pid}/compliance").json()
    # 预设已生成契约 → 不应再出现 create_contract；验证建议项包含 AGENTS.md
    assert "contract" in [c["key"] for c in rep["checks"] if not c["required"]]


def test_cli_contract_context_log_status(tmp_path, capsys):
    proj = tmp_path / "项目1-软件-CLI项目"
    proj.mkdir()
    (proj / "VERSION").write_text("0.5.0\n", encoding="utf-8")
    root = str(tmp_path)

    assert cli.main(["--root", root, "contract", "CLI项目", "--force"]) == 0
    assert (proj / "AGENTS.md").is_file()

    assert cli.main(["--root", root, "log", "CLI项目", "--agent", "codex",
                     "--action", "CLI测试", "--result", "done", "--summary", "ok"]) == 0
    assert cli.main(["--root", root, "logs", "CLI项目"]) == 0
    out = capsys.readouterr().out
    assert "CLI测试" in out and "ok" in out

    assert cli.main(["--root", root, "status", "CLI项目"]) == 0
    out = capsys.readouterr().out
    assert '"version": "0.5.0"' in out

    assert cli.main(["--root", root, "context", "项目1-软件-CLI项目"]) == 0
    out = capsys.readouterr().out
    assert "版本号唯一来源" in out and "0.5.0" in out
