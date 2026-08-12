from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import projectdock.update as update


def test_version_tuple_compare():
    assert update.version_tuple("0.10.0") > update.version_tuple("0.9.9")
    assert update.version_tuple("v0.4.0") == update.version_tuple("0.4.0")
    assert update.version_tuple("1.2.3") == update.version_tuple("1.2.3")


def _gh_result(code, payload):
    return subprocess.CompletedProcess(args=[], returncode=code,
                                       stdout=json.dumps(payload), stderr="")


def test_check_update_newer_available(monkeypatch):
    monkeypatch.setattr(update, "_gh", lambda *a, **k: _gh_result(0, {
        "tagName": "v0.5.0", "body": "修复若干 bug", "publishedAt": "2026-08-12", "url": "https://x"}))
    r = update.check_update("0.4.0", "GinyvaXu/ProjectDock")
    assert r["status"] == "ok"
    assert r["update_available"] is True
    assert r["latest"] == "0.5.0"
    assert "修复" in r["notes"]


def test_check_update_current_latest(monkeypatch):
    monkeypatch.setattr(update, "_gh", lambda *a, **k: _gh_result(0, {"tagName": "v0.4.0", "body": ""}))
    r = update.check_update("0.4.0", "GinyvaXu/ProjectDock")
    assert r["update_available"] is False and r["latest"] == "0.4.0"


def test_check_update_unknown_when_gh_fails(monkeypatch):
    monkeypatch.setattr(update, "_gh", lambda *a, **k: _gh_result(1, {"tagName": "x"}))
    monkeypatch.setattr(update, "urllib", None) if False else None

    def fake_urlopen(url, timeout=0):
        raise OSError("no net")
    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    r = update.check_update("0.4.0", "GinyvaXu/ProjectDock")
    assert r["status"] == "unknown" and r["update_available"] is False


def test_download_setup_ok(tmp_path, monkeypatch):
    dest = tmp_path / "dl"
    dest.mkdir()
    (dest / "ProjectDock_Setup_v0.5.0.exe").write_bytes(b"setup")
    monkeypatch.setattr(update, "_gh", lambda *a, **k: _gh_result(0, {}))
    r = update.download_setup("GinyvaXu/ProjectDock", "v0.5.0", dest)
    assert r["ok"] and r["path"].endswith(".exe") and r["size"] > 0


def test_download_setup_missing(tmp_path, monkeypatch):
    dest = tmp_path / "dl2"
    dest.mkdir()
    monkeypatch.setattr(update, "_gh", lambda *a, **k: _gh_result(0, {}))
    r = update.download_setup("GinyvaXu/ProjectDock", "v0.5.0", dest)
    assert r["ok"] is False and "未找到" in r["error"]


def test_install_setup_commands(monkeypatch, tmp_path):
    fake = tmp_path / "Setup.exe"
    fake.write_bytes(b"x")
    captured = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

    monkeypatch.setattr(update.subprocess, "Popen", FakePopen)
    r = update.install_setup(str(fake))
    assert r["ok"] is True
    assert captured["cmd"][0] == str(fake)
    assert "/VERYSILENT" in captured["cmd"] and "/SUPPRESSMSGBOXES" in captured["cmd"]
    # 非 exe / 不存在 -> 拒绝
    assert update.install_setup(str(tmp_path / "nope.txt"))["ok"] is False


# ---------- API ----------

def test_api_update_check(client, monkeypatch):
    import projectdock.api as api_mod
    monkeypatch.setattr(api_mod.update, "check_update", lambda *a, **k: {
        "status": "ok", "current": "0.4.0", "latest": "0.5.0",
        "update_available": True, "notes": "新功能", "published_at": "", "url": "", "repo": "x"})
    r = client.get("/api/update/check")
    assert r.status_code == 200
    assert r.json()["update_available"] is True and r.json()["latest"] == "0.5.0"


def test_api_update_download(client, monkeypatch):
    import projectdock.api as api_mod
    monkeypatch.setattr(api_mod.update, "latest_release", lambda repo: {"tag": "v0.5.0"})
    monkeypatch.setattr(api_mod.update, "download_setup",
                        lambda repo, tag, dest: {"ok": True, "path": "C:/t/Setup.exe", "size": 1024})
    r = client.post("/api/update/download")
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["size"] == 1024


def test_api_update_download_no_release(client, monkeypatch):
    import projectdock.api as api_mod
    monkeypatch.setattr(api_mod.update, "latest_release", lambda repo: None)
    assert client.post("/api/update/download").status_code == 400


def test_api_update_install(client, monkeypatch):
    import projectdock.api as api_mod
    monkeypatch.setattr(api_mod.update, "install_setup", lambda p: {"ok": True, "error": ""})
    r = client.post("/api/update/install", json={"path": "C:/t/Setup.exe"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_settings_update_repo_roundtrip(client):
    r = client.put("/api/settings", json={"update_repo": "other/repo"})
    assert r.status_code == 200
    assert client.get("/api/settings").json()["update_repo"] == "other/repo"
