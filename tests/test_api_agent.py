"""API 直连 AI 后端（api_agent）与 AI 接入设置测试。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from projectdock import api_agent as aa


# ---------- 工具执行 ----------

def test_normalize_base_url():
    assert aa.normalize_base_url("https://api.deepseek.com/") == "https://api.deepseek.com"
    assert aa.normalize_base_url("https://api.deepseek.com/v1/chat/completions") == "https://api.deepseek.com/v1"
    assert aa.normalize_base_url("") == ""


def test_headers_opencode_go_compat():
    h = aa._headers("sk-x", "https://opencode.ai/zen/go/v1")
    assert h["Authorization"] == "Bearer sk-x"
    assert h["x-opencode-session"] == "projectdock"  # 网关必需路由头
    assert "User-Agent" in h and "Mozilla" in h["User-Agent"]  # 绕过 Cloudflare 1010
    h2 = aa._headers("sk-x", "https://api.deepseek.com")
    assert "x-opencode-session" not in h2


def test_tools_file_ops(tmp_path):
    out, summary = aa.execute_tool(tmp_path, "write_file", {"path": "docs/a.md", "content": "# A\n内容"})
    assert "已写入" in out and (tmp_path / "docs" / "a.md").is_file()
    out, _ = aa.execute_tool(tmp_path, "read_file", {"path": "docs/a.md"})
    assert "# A" in out
    out, summary = aa.execute_tool(tmp_path, "list_dir", {"path": "."})
    assert "docs/" in out
    # 覆盖写会备份 .bak
    aa.execute_tool(tmp_path, "write_file", {"path": "docs/a.md", "content": "# A2"})
    assert (tmp_path / "docs" / "a.md.bak").read_text(encoding="utf-8") == "# A\n内容"


def test_tools_path_escape_blocked(tmp_path):
    out, summary = aa.execute_tool(tmp_path, "write_file", {"path": "../evil.txt", "content": "x"})
    assert "拒绝" in summary and "越界" in out
    assert not (tmp_path.parent / "evil.txt").exists()
    out, _ = aa.execute_tool(tmp_path, "read_file", {"path": "..\\..\\windows\\win.ini"})
    assert "越界" in out


def test_tool_run_command(tmp_path):
    out, summary = aa.execute_tool(tmp_path, "run_command", {"command": "echo pd-api-test"})
    assert "pd-api-test" in out and "退出码 0" in summary
    out, _ = aa.execute_tool(tmp_path, "run_command", {"command": "exit 3"})
    assert "退出码 3" in out


# ---------- Agent 循环 ----------

def _fake_settings():
    return SimpleNamespace(api_base_url="https://api.deepseek.com", api_key="sk-test", api_model="deepseek-chat")


def test_run_api_agent_loop(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_chat(base, key, model, messages, tools, on_text, timeout=120):
        calls["n"] += 1
        if calls["n"] == 1:
            on_text("先写文件。")
            return {"content": "先写文件。",
                    "tool_calls": [{"id": "c1", "name": "write_file",
                                    "arguments": json.dumps({"path": "x.md", "content": "# X"})}],
                    "finish_reason": "tool_calls"}
        on_text("完成。")
        return {"content": "完成。", "tool_calls": [], "finish_reason": "stop"}

    monkeypatch.setattr(aa, "chat_stream", fake_chat)
    events = []
    aa.run_api_agent(_fake_settings(), tmp_path, "生成 x.md", events.append, context="ctx")
    assert (tmp_path / "x.md").read_text(encoding="utf-8") == "# X"
    kinds = [e.get("type") for e in events]
    assert "chunk" in kinds and "status" in kinds
    text = "".join(e.get("text", "") for e in events if e.get("type") == "chunk")
    assert "完成" in text


def test_run_api_agent_unconfigured(tmp_path):
    settings = SimpleNamespace(api_base_url="", api_key="", api_model="")
    with pytest.raises(aa.ApiAgentError):
        aa.run_api_agent(settings, tmp_path, "x", lambda e: None)


def test_run_api_agent_tool_error_fed_back(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_chat(base, key, model, messages, tools, on_text, timeout=120):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": "", "tool_calls": [{"id": "c1", "name": "read_file",
                                                   "arguments": json.dumps({"path": "../x"})}],
                    "finish_reason": "tool_calls"}
        # 第二次调用时，历史里应带有工具的拒绝结果
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs and "越界" in tool_msgs[-1]["content"]
        return {"content": "ok", "tool_calls": [], "finish_reason": "stop"}

    monkeypatch.setattr(aa, "chat_stream", fake_chat)
    aa.run_api_agent(_fake_settings(), tmp_path, "t", lambda e: None)
    assert calls["n"] == 2


# ---------- API 端点 ----------

def test_agents_endpoint_includes_api(client):
    agents = client.get("/api/agents").json()
    assert [a["name"] for a in agents] == ["claude", "pi", "api"]


def test_settings_api_roundtrip(client):
    saved = client.get("/api/settings").json()
    assert saved["api_base_url"] and saved["api_model"]
    assert saved["api_key_set"] is False and saved["api_configured"] is False
    assert "api_key" not in saved  # Key 不回显
    r = client.put("/api/settings", json={"api_key": "sk-test-123"})
    assert r.status_code == 200
    assert r.json()["api_key_set"] is True and r.json()["api_configured"] is True
    bad = client.put("/api/settings", json={"api_base_url": "ftp://x"})
    assert bad.status_code == 400
    cleared = client.put("/api/settings", json={"api_key": ""})
    assert cleared.json()["api_configured"] is False


def test_ai_test_endpoint(client, monkeypatch):
    from projectdock import api_agent
    r = client.post("/api/ai/test", json={"base_url": "https://x", "api_key": ""})
    assert r.status_code == 400  # 无 Key
    monkeypatch.setattr(api_agent, "list_models", lambda base, key, timeout=30: ["m1", "m2"])
    r2 = client.post("/api/ai/test", json={"base_url": "https://api.deepseek.com", "api_key": "sk-x"})
    assert r2.status_code == 200 and r2.json()["models"] == ["m1", "m2"]


def test_agent_run_api_unconfigured_guard(client, state):
    root = state.settings.root
    (root / "Project1-软件-A").mkdir()
    r = client.post("/api/agent/run", json={"project_id": "Project1-软件-A", "prompt": "x", "agent": "api"})
    assert r.status_code == 400
    assert "API 接入" in r.json()["detail"]
