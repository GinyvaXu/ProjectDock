from __future__ import annotations

import json
from pathlib import Path

import pytest

import projectdock.cli as cli
from projectdock import agent as agent_mod
from projectdock import contract, presets
from projectdock.compliance import archive_root_dist
from projectdock.config import Settings
from projectdock.db import connect, list_projects, upsert_custom_type


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    """把 CLI 的设置/DB 指向临时目录，root 指向临时资料库。"""
    data_dir = tmp_path / "data"
    root = tmp_path / "lib"
    root.mkdir()
    settings = Settings(data_dir)
    monkeypatch.setattr(cli, "_app_settings", lambda: Settings(data_dir))
    monkeypatch.setattr(cli, "_db", lambda: connect(data_dir / "data.db"))
    return {"root": root, "settings": settings, "data_dir": data_dir}


def _make_project(root: Path, name: str = "项目1-软件-测试") -> Path:
    proj = root / name
    proj.mkdir()
    (proj / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    return proj


def test_confirm_policy_defaults(tmp_path):
    s = Settings(tmp_path / "data")
    for key in ("push", "delete", "github_create", "release", "archive"):
        assert s.confirm_required(key) is True, key
    s.update(confirm_policy={"push": False})
    assert s.confirm_required("push") is False
    assert s.confirm_required("release") is True
    assert s.as_dict()["confirm_policy"]["delete"] is True


def test_confirm_policy_api_roundtrip(client):
    resp = client.put("/api/settings", json={"confirm_policy": {"push": False, "archive": False}})
    assert resp.status_code == 200
    saved = client.get("/api/settings").json()
    policy = saved["confirm_policy"]
    assert policy["push"] is False and policy["archive"] is False
    assert policy["delete"] is True and policy["release"] is True and policy["github_create"] is True


def test_contract_contains_confirm_policy():
    text = contract.contract_for("软件", presets.PRESETS["软件"], "测试项目")
    assert "确认策略" in text
    assert "推送 GitHub" in text and "删除文件" in text
    assert "projectdock.cli init" in text and "projectdock.cli release" in text
    generic = contract.contract_for("网站", presets.PRESETS["网站"], "站点")
    assert "确认策略" in generic and "--confirm" in generic


def test_agent_prompt_injects_policy():
    prompt = agent_mod.system_prompt("甲", "C:/x", {"name": "软件", "label": "软件"},
                                     confirm_policy={"push": True, "release": True, "archive": False})
    assert "确认策略" in prompt
    assert "推送 GitHub" in prompt and "发布 Release" in prompt
    auto = agent_mod.system_prompt("乙", "C:/y", None, confirm_policy={"push": False, "delete": False})
    assert "允许自动执行" in auto
    none = agent_mod.system_prompt("丙", "C:/z", None, None)
    assert "确认策略" not in none


def test_cli_init_builtin(cli_env):
    cli.main(["--root", str(cli_env["root"]), "init", "新项目甲", "--type", "软件", "--no-git"])
    proj = cli_env["root"] / "项目1-软件-新项目甲"
    assert proj.is_dir()
    assert (proj / "README.md").is_file() and (proj / "VERSION").is_file()
    assert (proj / "AGENTS.md").is_file()
    conn = connect(cli_env["data_dir"] / "data.db")
    ids = [p["id"] for p in list_projects(conn)]
    assert "项目1-软件-新项目甲" in ids


def test_cli_init_custom_type(cli_env):
    conn = connect(cli_env["data_dir"] / "data.db")
    upsert_custom_type(conn, "数据分析", "数据分析", "数据项目", ["data", "notebooks"], {"README.md": "# {title}\n"}, True)
    cli.main(["--root", str(cli_env["root"]), "init", "分析乙", "--type", "数据分析", "--no-git"])
    proj = cli_env["root"] / "项目1-数据分析-分析乙"
    assert (proj / "data").is_dir() and (proj / "notebooks").is_dir()
    assert (proj / "README.md").is_file()


def test_cli_archive_requires_confirm(cli_env):
    proj = _make_project(cli_env["root"])
    d = proj / "dist"
    d.mkdir()
    (d / "app.exe").write_bytes(b"exe")
    with pytest.raises(SystemExit):
        cli.main(["--root", str(cli_env["root"]), "archive", proj.name])
    assert (d / "app.exe").exists()  # 未确认不移动
    assert not (proj / "versions").exists()


def test_cli_archive_with_confirm(cli_env):
    proj = _make_project(cli_env["root"])
    d = proj / "dist"
    d.mkdir()
    (d / "app.exe").write_bytes(b"exe")
    cli.main(["--root", str(cli_env["root"]), "archive", proj.name, "--confirm"])
    assert not (d / "app.exe").exists()
    assert (proj / "versions" / "v0.1.0" / "dist" / "app.exe").exists()


def test_cli_archive_version_override(tmp_path):
    proj = tmp_path / "项目1-软件-归档"
    proj.mkdir()
    (proj / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (proj / "dist").mkdir()
    (proj / "dist" / "app.exe").write_bytes(b"exe")
    result = archive_root_dist(proj, version="9.9.9")
    assert result["ok"]
    assert (proj / "versions" / "v9.9.9" / "dist" / "app.exe").exists()


def test_cli_release_requires_confirm(cli_env, monkeypatch):
    proj = _make_project(cli_env["root"])
    called = []

    async def fake_release(state, project_path, cfg, emit):
        called.append(cfg)

    monkeypatch.setattr(cli.release, "run_release", fake_release)
    with pytest.raises(SystemExit):
        cli.main(["--root", str(cli_env["root"]), "release", proj.name, "--version", "1.2.3", "--push"])
    assert called == []  # 未确认不发布
    with pytest.raises(SystemExit):
        cli.main(["--root", str(cli_env["root"]), "release", proj.name, "--version", "bad", "--push", "--confirm"])
    assert called == []  # 版本号非法不发布


def test_cli_release_with_confirm(cli_env, monkeypatch):
    proj = _make_project(cli_env["root"])
    captured = {}

    async def fake_release(state, project_path, cfg, emit):
        captured["cfg"] = cfg
        captured["project"] = str(project_path)
        emit("[fake] release")

    monkeypatch.setattr(cli.release, "run_release", fake_release)
    cli.main(["--root", str(cli_env["root"]), "release", proj.name, "--version", "1.2.3", "--push", "--confirm",
              "--changelog", "新增确认策略"])
    assert captured["cfg"]["version"] == "1.2.3"
    assert captured["cfg"]["push"] is True
    assert captured["cfg"]["changelog"] == "新增确认策略"
    logs = list((proj / "logs" / "ai").glob("*.json"))
    assert len(logs) == 1
    entry = json.loads(logs[0].read_text(encoding="utf-8"))
    assert entry["result"] == "done" and "1.2.3" in entry["action"]


def test_cli_build_runs_and_archives(cli_env):
    proj = _make_project(cli_env["root"])
    (proj / "build.py").write_text('print("build ok")', encoding="utf-8")
    d = proj / "dist"
    d.mkdir()
    (d / "app.exe").write_bytes(b"exe")
    cli.main(["--root", str(cli_env["root"]), "build", proj.name, "--archive", "--confirm"])
    assert not (d / "app.exe").exists()
    assert (proj / "versions" / "v0.1.0" / "dist" / "app.exe").exists()
    logs = list((proj / "logs" / "ai").glob("*.json"))
    assert len(logs) >= 1
