"""opencode 桥接（opencode v2 后台服务）：会话对话 / SSE 事件流 / PTY 终端。

- 服务发现：`~/.config/opencode/service.json`（密码）+ `opencode service status`（端口，带缓存）；
- 鉴权：HTTP Basic（用户名固定 `opencode`，密码取自 service.json）；
- 会话：每个项目目录一个 opencode 会话（id 存 PD 数据库 projects.oc_session，可续聊）；
- 事件流：订阅 `/api/event`（SSE），按 sessionID 过滤，映射为 PD 的 chunk/status/line 事件；
- PTY：由 opencode 服务托管（`/api/pty`），WebSocket 代理在 api.py；本模块负责创建/查询/删除/改尺寸。

仅依赖标准库（urllib）；不打印/不落盘任何凭据。
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

SERVICE_CONFIG = Path.home() / ".config" / "opencode" / "service.json"
SERVICE_USER = "opencode"
STATUS_TTL = 15.0          # 服务地址缓存秒数
DEFAULT_TIMEOUT = 60
CHAT_TIMEOUT = 1800        # 单条消息最长等待（30 分钟）
IDLE_TIMEOUT = 600         # 无事件最长等待（10 分钟）
PTY_TITLE_PREFIX = "PD"    # ProjectDock 创建的终端标题前缀（用于复用识别）

_status_cache: dict = {"at": 0.0, "url": "", "ok": False}


class OcError(Exception):
    """opencode 服务不可用 / 请求失败。"""


# ---------------------------------------------------------------- 服务发现

def _read_password() -> str:
    try:
        data = json.loads(SERVICE_CONFIG.read_text(encoding="utf-8"))
        return str(data.get("password") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def auth_header() -> str:
    pw = _read_password()
    return "Basic " + base64.b64encode(f"{SERVICE_USER}:{pw}".encode()).decode()


def _headers(extra: dict | None = None) -> dict:
    h = {"Authorization": auth_header(), "Accept": "application/json", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _opencode_cmd(args: list[str]) -> list[str]:
    """opencode CLI 调用（Windows 下 npm 包装为 .cmd，需经 cmd 执行）。"""
    exe = shutil.which("opencode") or "opencode"
    low = str(exe).lower()
    if os.name == "nt" and low.endswith((".cmd", ".bat")):
        return ["cmd", "/c", str(exe), *args]
    if os.name == "nt" and low.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(exe), *args]
    return [str(exe), *args]


def _run_opencode(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(_opencode_cmd(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=0x08000000 if os.name == "nt" else 0)


def _service_url(force: bool = False) -> str:
    """当前后台服务地址（带缓存）；不可用返回空串。"""
    now = time.time()
    if not force and _status_cache["url"] and now - _status_cache["at"] < STATUS_TTL:
        return _status_cache["url"]
    url = ""
    try:
        proc = _run_opencode(["service", "status"], timeout=15)
        m = re.search(r"https?://[0-9.:\[\]]+", proc.stdout or "")
        if proc.returncode == 0 and m:
            url = m.group(0).rstrip("/")
    except (OSError, subprocess.TimeoutExpired):
        url = ""
    _status_cache.update({"at": now, "url": url, "ok": bool(url)})
    return url


def start_service() -> dict:
    """尝试启动 opencode 后台服务，返回最新状态。"""
    try:
        _run_opencode(["service", "start"], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcError(f"无法启动 opencode 服务：{exc}") from exc
    for _ in range(20):
        url = _service_url(force=True)
        if url:
            break
        time.sleep(0.5)
    return status()


def status() -> dict:
    """服务状态：{available, url, version, error}。"""
    url = _service_url(force=True)
    if not url:
        return {"available": False, "url": "", "version": "", "error": "opencode 后台服务未运行"}
    try:
        st, data = _request("GET", "/api/info", base_url=url, timeout=10)
        if st == 200 and isinstance(data, dict):
            return {"available": True, "url": url, "version": str(data.get("version") or ""), "error": ""}
        return {"available": False, "url": url, "version": "", "error": f"HTTP {st}"}
    except OcError as exc:
        return {"available": False, "url": url, "version": "", "error": str(exc)}


def available() -> bool:
    return bool(status().get("available"))


# ---------------------------------------------------------------- HTTP

def _request(method: str, path: str, body: dict | None = None, base_url: str | None = None,
             timeout: int = DEFAULT_TIMEOUT) -> tuple[int, object]:
    base = base_url or _service_url()
    if not base:
        raise OcError("opencode 后台服务未运行（可运行 opencode service start）")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, None
            try:
                return resp.status, json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(400).decode("utf-8", "replace")
        raise OcError(f"opencode HTTP {exc.code}：{detail[:200]}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        _status_cache.update({"at": 0.0, "url": "", "ok": False})  # 让下次重新探测
        raise OcError(f"连接 opencode 失败：{exc}") from exc


def _location_query(directory: str) -> str:
    return "location[directory]=" + urllib.parse.quote(str(directory))


# ---------------------------------------------------------------- 会话（对话）

def parse_model(model_ref: str) -> dict:
    """'provider/model' → {providerID, id}。"""
    text = str(model_ref or "").strip()
    if "/" in text:
        provider, _, mid = text.partition("/")
        return {"providerID": provider.strip(), "id": mid.strip()}
    return {"providerID": "opencode-go", "id": text or "deepseek-v4.1-flash"}


def create_session(directory: str, title: str, model_ref: str = "") -> str:
    body: dict = {"title": title, "location": {"directory": str(directory)}}
    if model_ref:
        body["model"] = parse_model(model_ref)
    st, data = _request("POST", "/api/session", body)
    sid = ((data or {}).get("data") or {}).get("id") if isinstance(data, dict) else None
    if st not in (200, 201) or not sid:
        raise OcError(f"创建 opencode 会话失败：{str(data)[:200]}")
    return str(sid)


def session_ok(sid: str) -> bool:
    try:
        st, data = _request("GET", f"/api/session/{sid}", timeout=15)
        return st == 200 and isinstance(data, dict) and bool((data.get("data") or {}).get("id"))
    except OcError:
        return False


def prompt(sid: str, text: str) -> None:
    st, data = _request("POST", f"/api/session/{sid}/prompt", {"text": text}, timeout=30)
    if st not in (200, 201):
        raise OcError(f"发送失败：{str(data)[:200]}")


def interrupt(sid: str) -> None:
    try:
        _request("POST", f"/api/session/{sid}/interrupt", {}, timeout=15)
    except OcError:
        pass


def permission_reply(sid: str, request_id: str, decision: str = "once") -> None:
    try:
        _request("POST", f"/api/session/{sid}/permission/{request_id}/reply", {"decision": decision}, timeout=15)
    except OcError:
        pass


def list_messages(sid: str) -> list[dict]:
    try:
        st, data = _request("GET", f"/api/session/{sid}/message", timeout=20)
    except OcError:
        return []
    items = ((data or {}).get("data") or []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


# ---------------------------------------------------------------- 事件流（对话流式）

def iter_events(timeout: int = CHAT_TIMEOUT) -> Iterator[dict]:
    """订阅 /api/event（SSE），逐条 yield 解析后的事件（阻塞；调用方放到线程里）。"""
    base = _service_url()
    if not base:
        raise OcError("opencode 后台服务未运行")
    req = urllib.request.Request(base + "/api/event",
                                 headers={"Authorization": auth_header(), "Accept": "text/event-stream"},
                                 method="GET")
    deadline = time.time() + timeout
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while time.time() < deadline:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").strip()
                if not text.startswith("data:"):
                    continue
                payload = text[5:].strip()
                if not payload:
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise OcError(f"事件流中断：{exc}") from exc


def _tool_line(event: dict) -> str:
    data = event.get("data") or {}
    name = str(data.get("name") or data.get("tool") or "工具")
    content = data.get("content")
    detail = ""
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("text"):
                detail = str(part["text"])
                break
    if not detail:
        detail = str(data.get("title") or "")
    return f"⚙ {name}" + (f"：{detail[:160]}" if detail else "")


def run_chat_task(settings, conn, project_path: Path, prompt_text: str, emit: Callable[[object], None]) -> None:
    """执行一次 opencode 对话任务（阻塞）：复用/创建会话 → 发送 → 流式回传 → 收尾。

    emit 事件与 PD 现有后端一致：status / chunk / line。
    """
    from .db import get_project, set_oc_session

    directory = str(Path(project_path).resolve())
    pid = Path(project_path).name
    row = get_project(conn, pid) or {}
    sid = str(row.get("oc_session") or "")
    model_ref = str(getattr(settings, "oc_model", "") or "")

    if not sid or not session_ok(sid):
        emit({"type": "status", "text": "正在创建 opencode 会话…"})
        sid = create_session(directory, f"ProjectDock · {pid}", model_ref)
        set_oc_session(conn, pid, sid)
    else:
        emit({"type": "status", "text": "正在使用已有 opencode 会话…"})

    emit({"type": "status", "text": f"已发送，等待 opencode 处理（会话 {sid[:14]}…）…"})
    prompt(sid, prompt_text)

    deadline = time.time() + CHAT_TIMEOUT
    last_event = time.time()
    started = False
    finished = False
    try:
        for event in iter_events(timeout=CHAT_TIMEOUT):
            if time.time() > deadline:
                break
            etype = str(event.get("type") or "")
            data = event.get("data") or {}
            if str(data.get("sessionID") or "") != sid and sid not in json.dumps(data, ensure_ascii=False):
                continue
            last_event = time.time()
            if not started and etype in ("session.execution.started", "session.step.started"):
                started = True
                emit({"type": "status", "text": "opencode 正在处理…"})
            if etype == "session.text.delta":
                emit({"type": "chunk", "text": str(data.get("delta") or "")})
            elif etype == "session.tool.progress":
                emit({"type": "status", "text": _tool_line(event)})
            elif etype == "session.tool.success":
                emit({"type": "line", "text": _tool_line(event)})
            elif etype in ("session.permission.requested", "permission.requested"):
                rid = str(data.get("id") or data.get("requestID") or "")
                action = str(data.get("action") or data.get("title") or "")
                if rid:
                    permission_reply(sid, rid, "once")
                    emit({"type": "line", "text": f"⚠ 已自动允许一次：{action[:120]}"})
            elif etype == "session.execution.succeeded":
                finished = True
                break
            elif etype == "session.execution.failed":
                err = (data.get("error") or {})
                msg = str(err.get("message") or err) if isinstance(err, dict) else str(err)
                raise OcError(f"opencode 执行失败：{msg[:200]}")
            elif etype == "session.step.failed":
                err = (data.get("error") or {})
                msg = str(err.get("message") or err) if isinstance(err, dict) else str(err)
                raise OcError(f"opencode 步骤失败：{msg[:200]}")
            if time.time() - last_event > IDLE_TIMEOUT:
                interrupt(sid)
                raise OcError("opencode 长时间无响应，已中断")
    except OcError:
        interrupt(sid)
        raise
    finally:
        emit({"type": "status", "text": ""})
    if not finished:
        emit({"type": "line", "text": "（任务已结束）"})


# ---------------------------------------------------------------- PTY（终端）

def list_ptys(directory: str) -> list[dict]:
    try:
        st, data = _request("GET", "/api/pty?" + _location_query(directory), timeout=20)
    except OcError:
        return []
    items = ((data or {}).get("data") or []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def create_pty(directory: str, kind: str, cols: int = 100, rows: int = 30) -> dict:
    """创建 PTY：kind=opencode（跑 opencode TUI）或 shell（cmd）。返回 PTY 信息。"""
    title = f"{PTY_TITLE_PREFIX}-{kind}"
    if kind == "opencode":
        command, args = "cmd.exe", ["/k", "opencode"]
    else:
        command, args = "cmd.exe", []
    body = {
        "command": command, "args": args, "cwd": str(directory), "title": title,
        "size": {"cols": max(20, int(cols)), "rows": max(5, int(rows))},
    }
    st, data = _request("POST", "/api/pty?" + _location_query(directory), body, timeout=30)
    pty = ((data or {}).get("data") or {}) if isinstance(data, dict) else {}
    if st not in (200, 201) or not pty.get("id"):
        raise OcError(f"创建终端失败：{str(data)[:200]}")
    return pty


def delete_pty(directory: str, pty_id: str) -> None:
    try:
        _request("DELETE", f"/api/pty/{pty_id}?" + _location_query(directory), timeout=15)
    except OcError:
        pass


def resize_pty(directory: str, pty_id: str, cols: int, rows: int) -> None:
    try:
        _request("PUT", f"/api/pty/{pty_id}?" + _location_query(directory),
                 {"size": {"cols": max(20, int(cols)), "rows": max(5, int(rows))}}, timeout=15)
    except OcError:
        pass


def pty_ws_url(directory: str, pty_id: str) -> str:
    base = _service_url()
    if not base:
        raise OcError("opencode 后台服务未运行")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/api/pty/{pty_id}/connect?{_location_query(directory)}"
