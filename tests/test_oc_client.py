"""opencode 桥接（oc_client）与集成端点测试（离线，网络调用均被 monkeypatch）。"""
from __future__ import annotations

import base64
import json
import time

import pytest

from projectdock import oc_client


# ---------- 基础工具 ----------

def test_parse_model():
    assert oc_client.parse_model("opencode-go/deepseek-v4.1-flash") == {
        "providerID": "opencode-go", "id": "deepseek-v4.1-flash"}
    assert oc_client.parse_model("") == {"providerID": "opencode-go", "id": "deepseek-v4.1-flash"}


def test_auth_header_format(monkeypatch, tmp_path):
    cfg = tmp_path / "service.json"
    cfg.write_text(json.dumps({"password": "pw123"}), encoding="utf-8")
    monkeypatch.setattr(oc_client, "SERVICE_CONFIG", cfg)
    assert oc_client.auth_header() == "Basic " + base64.b64encode(b"opencode:pw123").decode()


def test_service_url_parsing(monkeypatch):
    class P:
        returncode = 0
        stdout = "http://127.0.0.1:49374\n"
    monkeypatch.setattr(oc_client, "_run_opencode", lambda args, timeout=15: P())
    monkeypatch.setattr(oc_client, "_status_cache", {"at": 0.0, "url": "", "ok": False})
    assert oc_client._service_url(force=True) == "http://127.0.0.1:49374"


def test_service_url_unavailable(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
    monkeypatch.setattr(oc_client, "_run_opencode", lambda args, timeout=15: P())
    monkeypatch.setattr(oc_client, "_status_cache", {"at": 0.0, "url": "", "ok": False})
    assert oc_client._service_url(force=True) == ""


def test_pty_ws_url(monkeypatch):
    monkeypatch.setattr(oc_client, "_service_url", lambda force=False: "http://127.0.0.1:49374")
    url = oc_client.pty_ws_url(r"C:\proj", "pty_abc")
    assert url.startswith("ws://127.0.0.1:49374/api/pty/pty_abc/connect?")
    assert "location[directory]=" in url
    assert "C%3A%5Cproj" in url


def test_location_query_encoding():
    assert oc_client._location_query(r"C:\a b") == "location[directory]=C%3A%5Ca%20b"


# ---------- API 端点（mock oc_client） ----------

def test_oc_status_endpoint(client, monkeypatch):
    monkeypatch.setattr(oc_client, "status", lambda: {"available": True, "url": "http://x", "version": "2.0.18", "error": ""})
    r = client.get("/api/oc/status")
    assert r.status_code == 200 and r.json()["available"] is True and r.json()["version"] == "2.0.18"


def test_oc_pty_endpoint(client, state, monkeypatch):
    (state.settings.root / "Project1-软件-A").mkdir()
    monkeypatch.setattr(oc_client, "list_ptys", lambda directory: [])
    monkeypatch.setattr(oc_client, "create_pty", lambda directory, kind, cols=100, rows=30: {
        "id": "pty_1", "title": f"PD-{kind}", "status": "running"})
    r = client.post("/api/projects/Project1-软件-A/oc/pty", json={"kind": "opencode"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "pty_1" and body["kind"] == "opencode"
    assert body["ws"].startswith("/api/oc/pty/pty_1/ws?directory=")
    # 复用：再次请求不新建（list 返回运行中的同名 PTY）
    monkeypatch.setattr(oc_client, "list_ptys", lambda directory: [
        {"id": "pty_old", "title": "PD-opencode", "status": "running"}])
    r2 = client.post("/api/projects/Project1-软件-A/oc/pty", json={"kind": "opencode"})
    assert r2.json()["id"] == "pty_old"
    # new=True 强制新建
    r3 = client.post("/api/projects/Project1-软件-A/oc/pty", json={"kind": "opencode", "new": True})
    assert r3.json()["id"] == "pty_1"


def test_oc_pty_create_error(client, state, monkeypatch):
    (state.settings.root / "Project1-软件-A").mkdir()
    monkeypatch.setattr(oc_client, "list_ptys", lambda directory: [])
    def boom(directory, kind, cols=100, rows=30):
        raise oc_client.OcError("服务不可用")
    monkeypatch.setattr(oc_client, "create_pty", boom)
    r = client.post("/api/projects/Project1-软件-A/oc/pty", json={"kind": "shell"})
    assert r.status_code == 400 and "服务不可用" in r.json()["detail"]


def test_agent_run_opencode_unavailable_guard(client, state, monkeypatch):
    (state.settings.root / "Project1-软件-A").mkdir()
    monkeypatch.setattr(oc_client, "available", lambda: False)
    r = client.post("/api/agent/run", json={"project_id": "Project1-软件-A", "prompt": "x", "agent": "opencode"})
    assert r.status_code == 400 and "opencode" in r.json()["detail"]


def test_agent_run_opencode_job(client, state, monkeypatch):
    (state.settings.root / "Project1-软件-A").mkdir()
    monkeypatch.setattr(oc_client, "available", lambda: True)
    seen = {}
    def fake_run(settings, conn, project_path, prompt, emit):
        seen["prompt"] = prompt
        emit({"type": "chunk", "text": "完成"})
    monkeypatch.setattr(oc_client, "run_chat_task", fake_run)
    r = client.post("/api/agent/run", json={"project_id": "Project1-软件-A", "prompt": "你好", "agent": "opencode"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    for _ in range(50):
        st = client.get(f"/api/jobs/{jid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done"
    assert "你好" in seen.get("prompt", "")


def test_agents_include_opencode(client):
    names = [a["name"] for a in client.get("/api/agents").json()]
    assert names == ["claude", "pi", "api", "opencode"]


def test_settings_oc_model_roundtrip(client):
    saved = client.get("/api/settings").json()
    assert saved["oc_model"] == "opencode-go/deepseek-v4.1-flash"
    r = client.put("/api/settings", json={"oc_model": "opencode-go/glm-5.3"})
    assert r.status_code == 200 and r.json()["oc_model"] == "opencode-go/glm-5.3"


# ---------- 内部函数（mock 网络） ----------

def test_session_helpers(monkeypatch):
    calls = []

    def fake_request(method, path, body=None, base_url=None, timeout=60):
        calls.append((method, path, body))
        if path == "/api/session":
            return 200, {"data": {"id": "ses_1"}}
        if path == "/api/session/ses_1":
            return 200, {"data": {"id": "ses_1"}}
        if path == "/api/session/ses_1/message":
            return 200, {"data": [{"id": "m1", "type": "assistant"}]}
        return 200, {}

    monkeypatch.setattr(oc_client, "_request", fake_request)
    sid = oc_client.create_session(r"C:\p", "标题", "opencode-go/deepseek-v4.1-flash")
    assert sid == "ses_1"
    assert oc_client.session_ok("ses_1") is True
    oc_client.prompt("ses_1", "hi")
    oc_client.interrupt("ses_1")
    oc_client.permission_reply("ses_1", "per_1", "once")
    msgs = oc_client.list_messages("ses_1")
    assert msgs and msgs[0]["id"] == "m1"
    assert any(c[1] == "/api/session" and (c[2] or {}).get("model") for c in calls)


def test_pty_helpers(monkeypatch):
    def fake_request(method, path, body=None, base_url=None, timeout=60):
        if method == "GET":
            return 200, {"data": [{"id": "pty_1", "title": "PD-shell", "status": "running"}]}
        if method == "POST":
            return 200, {"data": {"id": "pty_new", "title": "PD-opencode"}}
        return 204, None

    monkeypatch.setattr(oc_client, "_request", fake_request)
    items = oc_client.list_ptys(r"C:\p")
    assert items and items[0]["id"] == "pty_1"
    pty = oc_client.create_pty(r"C:\p", "opencode", cols=80, rows=24)
    assert pty["id"] == "pty_new"
    oc_client.delete_pty(r"C:\p", "pty_1")
    oc_client.resize_pty(r"C:\p", "pty_1", 90, 30)


def test_iter_events_sse(monkeypatch):
    class FakeResp:
        def __init__(self, lines):
            self.lines = [ln.encode() + b"\n" for ln in lines]

        def readline(self):
            return self.lines.pop(0) if self.lines else b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import urllib.request
    monkeypatch.setattr(oc_client, "_service_url", lambda force=False: "http://x")
    monkeypatch.setattr(oc_client, "auth_header", lambda: "Basic x")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp([": heartbeat", 'data: {"type": "a", "data": {}}', 'data: {"type": "b"}']))
    got = list(oc_client.iter_events(timeout=5))
    assert [e["type"] for e in got] == ["a", "b"]


def test_status_and_available(monkeypatch):
    monkeypatch.setattr(oc_client, "_service_url", lambda force=False: "http://x")
    monkeypatch.setattr(oc_client, "_request", lambda method, path, body=None, base_url=None, timeout=60: (200, {"version": "2.0.18"}))
    st = oc_client.status()
    assert st["available"] is True and st["version"] == "2.0.18"
    monkeypatch.setattr(oc_client, "status", lambda: {"available": True})
    assert oc_client.available() is True


def test_run_chat_task_event_mapping(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from projectdock.db import connect, upsert_project

    settings = SimpleNamespace(oc_model="opencode-go/deepseek-v4.1-flash")
    events = [
        {"type": "session.execution.started", "data": {"sessionID": "ses_9"}},
        {"type": "session.tool.success", "data": {"sessionID": "ses_9", "content": [{"type": "text", "text": "写入了 a.md"}]}},
        {"type": "session.text.delta", "data": {"sessionID": "ses_9", "delta": "完成"}},
        {"type": "session.execution.succeeded", "data": {"sessionID": "ses_9"}},
    ]
    monkeypatch.setattr(oc_client, "session_ok", lambda sid: False)
    monkeypatch.setattr(oc_client, "create_session", lambda directory, title, model_ref="": "ses_9")
    monkeypatch.setattr(oc_client, "prompt", lambda sid, text: None)
    monkeypatch.setattr(oc_client, "iter_events", lambda timeout=0: iter(events))

    conn = connect(tmp_path / "d.db")
    upsert_project(conn, tmp_path.name, tmp_path.name, "软件", str(tmp_path))
    out = []
    oc_client.run_chat_task(settings, conn, tmp_path, "写个文件", out.append)
    kinds = [e.get("type") for e in out]
    assert "chunk" in kinds and "line" in kinds
    text = "".join(e.get("text", "") for e in out if e.get("type") == "chunk")
    assert "完成" in text
    from projectdock.db import get_project
    assert get_project(conn, tmp_path.name)["oc_session"] == "ses_9"


def test_run_chat_task_failure(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from projectdock.db import connect, upsert_project

    settings = SimpleNamespace(oc_model="")
    events = [
        {"type": "session.execution.failed", "data": {"sessionID": "ses_9", "error": {"type": "provider.quota", "message": "Insufficient funds"}}},
    ]
    monkeypatch.setattr(oc_client, "session_ok", lambda sid: True)
    monkeypatch.setattr(oc_client, "prompt", lambda sid, text: None)
    monkeypatch.setattr(oc_client, "interrupt", lambda sid: None)
    monkeypatch.setattr(oc_client, "iter_events", lambda timeout=0: iter(events))
    conn = connect(tmp_path / "d.db")
    upsert_project(conn, tmp_path.name, tmp_path.name, "软件", str(tmp_path))
    from projectdock.db import set_oc_session
    set_oc_session(conn, tmp_path.name, "ses_9")
    with pytest.raises(oc_client.OcError):
        oc_client.run_chat_task(settings, conn, tmp_path, "x", lambda e: None)
