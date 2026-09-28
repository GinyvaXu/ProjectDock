"""API 直连 AI 后端（OpenAI 兼容）：贴入 API Key 即可用，无需安装 pi / claude。

- 请求：POST {base_url}/chat/completions（stream=true），支持 tool_calls 工具调用；
- 工具：list_dir / read_file / write_file / run_command —— 全部限定在项目目录内；
- 循环：模型输出 → 执行工具 → 回填结果 → 继续，直到完成或达到步数上限；
- 与 pi/claude 后端同待遇：任务前备份、流式回显、任务后报告与 AI 日志（由 agent.run_agent_task 统一负责）。

仅依赖标准库（urllib），不新增运行时依赖。API Key 只存本机设置、不写日志。
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

DEFAULT_TIMEOUT = 120
MAX_STEPS = 40
MAX_TOOL_RESULT = 20000
MAX_READ_BYTES = 40000
MAX_LIST_ENTRIES = 300
MAX_CMD_TIMEOUT = 600


class ApiAgentError(Exception):
    """API 直连失败（配置缺失 / 网络 / 服务端返回错误）。"""


def normalize_base_url(url: str) -> str:
    """规范化 Base URL：去尾斜杠；用户误带 /chat/completions 时自动剥掉。"""
    u = str(url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u.rstrip("/")


def _decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("gbk", errors="replace")


def _headers(api_key: str) -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        h["Authorization"] = "Bearer " + api_key
    return h


def list_models(base_url: str, api_key: str, timeout: int = 30) -> list[str]:
    """GET {base}/models，返回可用模型 id 列表（用于「测试连接」）。"""
    base = normalize_base_url(base_url)
    if not base:
        raise ApiAgentError("未填写 Base URL")
    req = urllib.request.Request(base + "/models", headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = _decode(exc.read())[:300] if hasattr(exc, "read") else str(exc)
        raise ApiAgentError(f"HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ApiAgentError(f"连接失败：{exc}") from exc
    items = data.get("data") if isinstance(data, dict) else None
    out = []
    for it in items or []:
        if isinstance(it, dict) and it.get("id"):
            out.append(str(it["id"]))
    return out


def chat_stream(base_url: str, api_key: str, model: str, messages: list[dict],
                tools: list[dict] | None, on_text: Callable[[str], None],
                timeout: int = DEFAULT_TIMEOUT) -> dict:
    """流式对话：文本增量经 on_text 回调；返回 {content, tool_calls, finish_reason}。"""
    base = normalize_base_url(base_url)
    payload: dict = {"model": model, "messages": messages, "stream": True}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=data, method="POST", headers=_headers(api_key))
    content_parts: list[str] = []
    calls: dict[int, dict] = {}
    finish_reason = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    chunk = json.loads(body)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0] or {}
                if choice.get("finish_reason"):
                    finish_reason = str(choice["finish_reason"])
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    content_parts.append(text)
                    on_text(text)
                for tc in delta.get("tool_calls") or []:
                    idx = int(tc.get("index") or 0)
                    slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = str(tc["id"])
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += str(fn["name"])
                    if fn.get("arguments"):
                        slot["arguments"] += str(fn["arguments"])
    except urllib.error.HTTPError as exc:
        detail = _decode(exc.read())[:500] if hasattr(exc, "read") else str(exc)
        raise ApiAgentError(f"HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ApiAgentError(f"请求失败：{exc}") from exc
    ordered = [calls[i] for i in sorted(calls)]
    for i, c in enumerate(ordered):
        if not c["id"]:
            c["id"] = f"call_{i}"
    return {"content": "".join(content_parts), "tool_calls": ordered, "finish_reason": finish_reason}


# ---------------------------------------------------------------- 工具执行（限定项目目录内）

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出项目内某个目录的文件与子目录（相对项目根）",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "相对项目根的目录路径，默认 ."}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目内文本文件的内容",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "相对项目根的文件路径"},
                "max_bytes": {"type": "integer", "description": "最多读取字节数，默认 40000"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入/覆盖项目内文件（自动创建父目录；覆盖已有文件前会先备份 .bak）",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "相对项目根的文件路径"},
                "content": {"type": "string", "description": "要写入的完整文本内容"}}, "required": ["path", "content"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在项目目录内运行命令（Windows 走 cmd；返回合并输出）",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 120，最大 600"}}, "required": ["command"]},
        },
    },
]


def _safe_path(project: Path, rel: str) -> Path:
    rel = str(rel or ".").strip().replace("\\", "/")
    p = (project / rel).resolve()
    try:
        p.relative_to(project.resolve())
    except ValueError:
        raise ApiAgentError(f"路径越界（只允许项目目录内）：{rel}") from None
    return p


def _tool_list_dir(project: Path, args: dict) -> tuple[str, str]:
    target = _safe_path(project, args.get("path") or ".")
    if not target.is_dir():
        return f"（不是目录：{args.get('path')}）", "列目录失败"
    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as exc:
        return f"（读取失败：{exc}）", "列目录失败"
    for c in children[:MAX_LIST_ENTRIES]:
        if c.name.startswith("."):
            continue
        if c.is_dir():
            entries.append(f"{c.name}/")
        else:
            try:
                entries.append(f"{c.name}  ({c.stat().st_size} B)")
            except OSError:
                entries.append(c.name)
    more = "" if len(children) <= MAX_LIST_ENTRIES else f"\n…（共 {len(children)} 项，已截断）"
    rel = target.relative_to(project.resolve())
    return ("目录 " + (str(rel) if str(rel) != "." else ".") + "：\n" + "\n".join(entries) + more, f"列目录 {rel}（{len(entries)} 项）")


def _tool_read_file(project: Path, args: dict) -> tuple[str, str]:
    target = _safe_path(project, args.get("path") or "")
    if not target.is_file():
        return f"（文件不存在：{args.get('path')}）", "读文件失败"
    limit = int(args.get("max_bytes") or MAX_READ_BYTES)
    limit = max(1, min(limit, 200000))
    try:
        raw = target.read_bytes()
    except OSError as exc:
        return f"（读取失败：{exc}）", "读文件失败"
    text = _decode(raw[:limit])
    suffix = "" if len(raw) <= limit else f"\n…（文件共 {len(raw)} 字节，已截断）"
    return text + suffix, f"读取 {args.get('path')}（{len(raw)} B）"


def _tool_write_file(project: Path, args: dict) -> tuple[str, str]:
    rel = str(args.get("path") or "").strip()
    if not rel:
        return "（缺少 path）", "写文件失败"
    target = _safe_path(project, rel)
    content = str(args.get("content") or "")
    note = ""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_file():
            try:
                bak = target.with_name(target.name + ".bak")
                bak.write_bytes(target.read_bytes())
                note = "（原文件已备份为 .bak）"
            except OSError:
                pass
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"（写入失败：{exc}）", "写文件失败"
    return f"已写入 {rel}（{len(content.encode('utf-8'))} 字节）{note}", f"写入 {rel}"


def _tool_run_command(project: Path, args: dict) -> tuple[str, str]:
    command = str(args.get("command") or "").strip()
    if not command:
        return "（缺少 command）", "命令失败"
    timeout = int(args.get("timeout") or DEFAULT_TIMEOUT)
    timeout = max(5, min(timeout, MAX_CMD_TIMEOUT))
    try:
        proc = subprocess.run(command, shell=True, cwd=str(project), capture_output=True,
                              timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        return f"（命令超时 {timeout}s）", f"命令超时：{command[:60]}"
    except OSError as exc:
        return f"（无法执行：{exc}）", "命令失败"
    out = _decode(proc.stdout or b"") + ("\n" + _decode(proc.stderr) if proc.stderr else "")
    out = out.strip() or "(无输出)"
    if len(out) > MAX_TOOL_RESULT:
        out = out[:MAX_TOOL_RESULT] + "\n…（输出已截断）"
    return f"退出码 {proc.returncode}\n{out}", f"命令（退出码 {proc.returncode}）：{command[:60]}"


def execute_tool(project: Path, name: str, args: dict) -> tuple[str, str]:
    """执行一次工具调用，返回 (回填给模型的结果文本, 给用户看的摘要)。"""
    handlers = {
        "list_dir": _tool_list_dir,
        "read_file": _tool_read_file,
        "write_file": _tool_write_file,
        "run_command": _tool_run_command,
    }
    handler = handlers.get(name)
    if not handler:
        return f"（未知工具：{name}）", f"未知工具 {name}"
    try:
        return handler(project, args)
    except ApiAgentError as exc:
        return f"（拒绝执行：{exc}）", f"拒绝：{exc}"


# ---------------------------------------------------------------- Agent 循环

TOOL_NOTE = (
    "\n\n## 工具使用（API 直连模式）\n"
    "你可以调用工具直接操作当前项目目录内的文件与命令：list_dir / read_file / write_file / run_command。\n"
    "- 所有路径都相对于项目根目录；write_file 覆盖前会自动备份 .bak；命令在项目目录内执行；\n"
    "- 先看现状再动手；完成任务后用中文简短报告你做了什么（不要只做介绍）。"
)


def run_api_agent(settings, project_path: Path, prompt: str, emit: Callable[[object], None],
                  context: str | None = None) -> None:
    """执行一次 API 直连任务（阻塞；调用方负责放到线程里跑）。emit 兼容 dict 事件。"""
    base_url = normalize_base_url(getattr(settings, "api_base_url", ""))
    api_key = str(getattr(settings, "api_key", "") or "")
    model = str(getattr(settings, "api_model", "") or "")
    if not base_url or not api_key or not model:
        raise ApiAgentError("尚未配置 API 接入（设置 → AI 接入：Base URL / 模型 / API Key）")
    project = Path(project_path).resolve()
    messages: list[dict] = [
        {"role": "system", "content": (context or "") + TOOL_NOTE},
        {"role": "user", "content": prompt},
    ]
    for step in range(1, MAX_STEPS + 1):
        emit({"type": "status", "text": f"正在思考（第 {step} 步）…"})
        result = chat_stream(base_url, api_key, model, messages, TOOLS,
                             on_text=lambda t: emit({"type": "chunk", "text": t}))
        calls = result["tool_calls"]
        if not calls:
            if result["content"]:
                emit({"type": "line", "text": ""})
            emit({"type": "status", "text": ""})
            return
        # 模型要求调用工具：先把助手消息（含 tool_calls）入历史
        messages.append({
            "role": "assistant",
            "content": result["content"] or None,
            "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                for c in calls
            ],
        })
        for c in calls:
            try:
                args = json.loads(c["arguments"] or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            emit({"type": "status", "text": f"正在调用工具 {c['name']}…"})
            out, summary = execute_tool(project, c["name"], args)
            emit({"type": "line", "text": f"⚙ {summary}"})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": out[:MAX_TOOL_RESULT]})
    emit({"type": "line", "text": f"（已达到步数上限 {MAX_STEPS}，任务结束）"})
