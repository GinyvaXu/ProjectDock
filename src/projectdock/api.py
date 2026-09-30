from __future__ import annotations

import asyncio
import base64
import json
import os
import queue as queue_module
import subprocess
import sys
import urllib.parse
from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agent as agent_mod
from . import (
    ailog,
    backup,
    builder,
    compliance,
    console,
    contract,
    ghrepo,
    github,
    iconmaker,
    naming,
    oc_client,
    presets,
    protocols,
    release,
    scanner,
    techstack,
    update,
    versioning,
)
from .agent import AGENTS
from .config import APP_NAME, APP_VERSION
from .db import (
    delete_custom_type,
    delete_project,
    get_custom_type,
    get_project,
    list_custom_types,
    list_projects,
    set_pinned,
    set_version_scheme,
    upsert_custom_type,
    upsert_project,
)
from .models import (
    AGENT_NAMES,
    PROJECT_TYPES,
    THEMES,
    AgentBatch,
    AgentRun,
    AILogCreate,
    AiTestPayload,
    BackupRestore,
    BuildRun,
    ComplianceFix,
    CustomTypeCreate,
    GithubAuthPayload,
    GithubCreatePayload,
    GithubSetRemotePayload,
    IconPayload,
    OcPtyCreate,
    OcPtyResize,
    OpenPath,
    OpenUrl,
    ProjectCreate,
    ProjectImport,
    ProjectInit,
    ProjectUpdate,
    ReleaseRun,
    SettingsUpdate,
    TechstackPayload,
    UpdateInstall,
)
from .state import AppState


def _locate_web_dir() -> Path:
    """定位前端目录：兼容源码运行与 PyInstaller 冻结模式（onedir 下前端在 _internal/web）。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "web")
    candidates.append(Path(__file__).resolve().parents[2] / "web")
    candidates.append(Path(sys.executable).resolve().parent / "web")
    for cand in candidates:
        if (cand / "index.html").is_file():
            return cand
    return candidates[0]


WEB_DIR = _locate_web_dir()


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(title=f"{APP_NAME} 项目坞", version=APP_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api = APIRouter(prefix="/api")
    app.state.pd_state = state

    def _resolve_project(pid: str) -> dict:
        row = get_project(state.conn, pid)
        if row and row.get("excluded"):
            raise HTTPException(status_code=404, detail="项目不存在")
        if row and Path(row["path"]).is_dir():
            return row
        p = state.settings.root / pid
        if p.is_dir():
            entry = scanner.parse_project_entry(pid)
            return {"id": pid, "name": pid, "type": (entry.ptype or "其他") if entry else "其他",
                    "path": str(p), "description": ""}
        raise HTTPException(status_code=404, detail="项目不存在")

    def _project_dir(pid: str) -> str:
        """项目目录绝对路径（供 opencode 作用域 / 终端使用）。"""
        proj = _resolve_project(pid)
        return str(Path(proj["path"]).resolve())

    def _type_spec(ptype: str) -> dict | None:
        if ptype in presets.PRESETS:
            spec = presets.PRESETS[ptype]
            return {
                "name": ptype, "label": spec["label"], "description": spec["description"],
                "dirs": spec.get("dirs", []), "files": spec.get("files", {}),
                "git": spec.get("git", True), "custom": False,
                "version_scheme": protocols.version_scheme_for(ptype),
            }
        row = get_custom_type(state.conn, ptype)
        if row:
            return {
                "name": row["name"], "label": row["label"], "description": row["description"],
                "dirs": json.loads(row["dirs"]), "files": json.loads(row["files"]),
                "git": bool(row["git"]), "custom": True,
                "version_scheme": protocols.version_scheme_for(ptype),
            }
        return None

    def _resolve_agent(requested: str | None) -> str:
        """解析 AI 后端：未知/缺省回落设置；api/opencode 未就绪时给出明确提示。"""
        agent = requested if requested in AGENT_NAMES else state.settings.agent
        if agent == "api" and not state.settings.api_configured:
            raise HTTPException(status_code=400, detail="尚未配置 API 接入：请在「设置 → AI 接入」填写 Base URL / 模型 / API Key")
        if agent == "opencode" and not oc_client.available():
            raise HTTPException(status_code=400, detail="opencode 后台服务未运行：可运行 opencode service start，或先打开 opencode 桌面版")
        return agent

    @api.get("/health")
    def health() -> dict:
        return {"ok": True, "app": APP_NAME, "version": APP_VERSION, "root": str(state.settings.root)}

    @api.get("/settings")
    def get_settings() -> dict:
        return state.settings.as_dict()

    @api.put("/settings")
    def put_settings(payload: SettingsUpdate) -> dict:
        if payload.agent is not None and payload.agent not in AGENT_NAMES:
            raise HTTPException(status_code=400, detail="未知的 agent")
        if payload.theme is not None and payload.theme not in THEMES:
            raise HTTPException(status_code=400, detail="未知的主题")
        if payload.github_visibility is not None and payload.github_visibility not in ("private", "public"):
            raise HTTPException(status_code=400, detail="未知的仓库可见性")
        if payload.naming_style is not None and payload.naming_style not in (naming.STYLE_AUTO, *naming.STYLES):
            raise HTTPException(status_code=400, detail="未知的命名规范风格")
        if payload.api_base_url is not None:
            text = payload.api_base_url.strip()
            if text and not text.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="API Base URL 需以 http:// 或 https:// 开头")
        return state.settings.update(
            root=payload.root, agent=payload.agent, theme=payload.theme,
            github_auto=payload.github_auto, github_visibility=payload.github_visibility,
            backup=payload.backup, type_tabs=payload.type_tabs,
            confirm_policy=payload.confirm_policy,
            update_repo=payload.update_repo,
            naming_style=payload.naming_style,
            api_base_url=payload.api_base_url, api_model=payload.api_model, api_key=payload.api_key,
            oc_model=payload.oc_model,
        )

    @api.post("/ai/test")
    def ai_test(payload: AiTestPayload | None = None) -> dict:
        """测试 API 接入（可传未保存的 Base URL / Key 覆盖设置）。"""
        from . import api_agent
        base_url = (payload.base_url if payload and payload.base_url else state.settings.api_base_url)
        api_key = (payload.api_key if payload and payload.api_key else state.settings.api_key)
        if not str(base_url or "").strip():
            raise HTTPException(status_code=400, detail="未填写 Base URL")
        if not str(api_key or "").strip():
            raise HTTPException(status_code=400, detail="未填写 API Key")
        try:
            models = api_agent.list_models(base_url, api_key)
        except api_agent.ApiAgentError as exc:
            raise HTTPException(status_code=400, detail=f"连接失败：{exc}")
        return {"ok": True, "models": models[:60], "count": len(models)}

    # ---------------- opencode 集成（内嵌终端 + 对话后端） ----------------

    @api.get("/oc/status")
    def oc_status() -> dict:
        """opencode 后台服务状态（终端 / 对话可用性）。"""
        return oc_client.status()

    @api.post("/oc/start")
    def oc_start() -> dict:
        try:
            return {"ok": True, **oc_client.start_service()}
        except oc_client.OcError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @api.get("/projects/{pid}/oc/ptys")
    def oc_ptys(pid: str) -> list[dict]:
        return oc_client.list_ptys(_project_dir(pid))

    @api.post("/projects/{pid}/oc/pty", status_code=201)
    def oc_create_pty(pid: str, payload: OcPtyCreate) -> dict:
        """创建/复用一个内嵌终端（opencode TUI 或 shell），返回 WebSocket 路径。"""
        kind = payload.kind if payload.kind in ("opencode", "shell") else "opencode"
        directory = _project_dir(pid)
        pty = None
        if not payload.new:
            for item in oc_client.list_ptys(directory):
                if str(item.get("title") or "") == f"PD-{kind}" and item.get("status") == "running":
                    pty = item
                    break
        if pty is None:
            try:
                pty = oc_client.create_pty(directory, kind, cols=payload.cols, rows=payload.rows)
            except oc_client.OcError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        ws_path = f"/api/oc/pty/{pty.get('id')}/ws?directory={urllib.parse.quote(directory)}"
        return {"id": pty.get("id"), "title": pty.get("title"), "kind": kind, "ws": ws_path}

    @api.delete("/projects/{pid}/oc/pty/{pty_id}")
    def oc_delete_pty(pid: str, pty_id: str) -> dict:
        oc_client.delete_pty(_project_dir(pid), pty_id)
        return {"ok": True}

    @api.post("/projects/{pid}/oc/pty/{pty_id}/resize")
    def oc_resize_pty(pid: str, pty_id: str, payload: OcPtyResize) -> dict:
        oc_client.resize_pty(_project_dir(pid), pty_id, payload.cols, payload.rows)
        return {"ok": True}

    @api.websocket("/oc/pty/{pty_id}/ws")
    async def oc_pty_ws(websocket: WebSocket, pty_id: str, directory: str = ""):
        """浏览器终端 ↔ opencode 托管 PTY 的双向代理（鉴权在服务端注入）。"""
        import websockets

        await websocket.accept()
        if not directory:
            await websocket.close(code=1008, reason="missing directory")
            return
        try:
            oc_url = oc_client.pty_ws_url(directory, pty_id)
        except oc_client.OcError as exc:
            await websocket.close(code=1011, reason=str(exc)[:120])
            return
        try:
            async with websockets.connect(oc_url, additional_headers={"Authorization": oc_client.auth_header()},
                                          max_size=None, ping_interval=None) as oc_ws:
                async def browser_to_oc() -> None:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            return
                        if msg.get("bytes") is not None:
                            await oc_ws.send(msg["bytes"])
                        elif msg.get("text") is not None:
                            await oc_ws.send(msg["text"])

                async def oc_to_browser() -> None:
                    async for message in oc_ws:
                        if isinstance(message, (bytes, bytearray)):
                            await websocket.send_bytes(bytes(message))
                        else:
                            await websocket.send_text(str(message))

                tasks = [asyncio.create_task(browser_to_oc()), asyncio.create_task(oc_to_browser())]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for t in tasks:
                        t.cancel()
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    @api.get("/naming/styles")
    def list_naming_styles() -> dict:
        """命名规范风格清单（供未来版本的「一键切换」界面使用）。"""
        root = state.settings.root
        return {
            "current": state.settings.naming_style,
            "detected": naming.detect_style(root),
            "auto": {"id": naming.STYLE_AUTO, "label": "自动识别",
                     "description": "按资料库现有项目文件夹自动选择风格", "example": ""},
            "styles": [style.as_dict() for style in naming.STYLES.values()],
        }

    @api.get("/presets")
    def list_presets() -> list[dict]:
        out = []
        for t, spec in presets.PRESETS.items():
            out.append({
                "type": t, "label": spec["label"], "description": spec["description"],
                "files": list(spec.get("files", {})), "dirs": list(spec.get("dirs", [])),
                "git": spec.get("git", True), "custom": False,
                "version_scheme": protocols.version_scheme_for(t),
            })
        for row in list_custom_types(state.conn):
            out.append({
                "type": row["name"], "label": row["label"], "description": row["description"],
                "files": list(json.loads(row["files"])), "dirs": json.loads(row["dirs"]),
                "git": bool(row["git"]), "custom": True,
                "version_scheme": protocols.version_scheme_for(row["name"]),
            })
        return out

    @api.get("/types")
    def list_types() -> list[dict]:
        override = state.settings.type_tabs
        out = []
        for t, spec in presets.PRESETS.items():
            out.append({
                "name": t, "label": spec["label"], "description": spec["description"],
                "dirs": spec.get("dirs", []), "files": spec.get("files", {}),
                "git": spec.get("git", True), "custom": False,
                "tabs": presets.tabs_for_type(t, override),
                "default_tabs": list(presets.DEFAULT_TABS.get(t, presets.DEFAULT_TABS["其他"])),
                "tab_labels": presets.TAB_LABELS,
                "version_scheme": protocols.version_scheme_for(t),
            })
        for row in list_custom_types(state.conn):
            ptype = row["name"]
            out.append({
                "name": ptype, "label": row["label"], "description": row["description"],
                "dirs": json.loads(row["dirs"]), "files": json.loads(row["files"]),
                "git": bool(row["git"]), "custom": True,
                "tabs": presets.tabs_for_type(ptype, override),
                "default_tabs": list(presets.DEFAULT_TABS.get(ptype, presets.DEFAULT_TABS["其他"])),
                "tab_labels": presets.TAB_LABELS,
                "version_scheme": protocols.version_scheme_for(ptype),
            })
        return out

    @api.post("/types", status_code=201)
    def create_type(payload: CustomTypeCreate) -> dict:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="类型名称不能为空")
        if name in presets.PRESETS:
            raise HTTPException(status_code=400, detail="与内置类型重名")
        label = (payload.label or name).strip()
        upsert_custom_type(state.conn, name, label, payload.description, payload.dirs, payload.files, payload.git)
        return {"name": name, "label": label, "description": payload.description,
                "dirs": payload.dirs, "files": payload.files, "git": payload.git, "custom": True}

    @api.delete("/types/{name}")
    def remove_type(name: str) -> dict:
        if name in presets.PRESETS:
            raise HTTPException(status_code=400, detail="内置类型不能删除")
        delete_custom_type(state.conn, name)
        return {"ok": True}

    @api.get("/projects")
    def list_all() -> list[dict]:
        root = state.settings.root
        root.mkdir(parents=True, exist_ok=True)
        db_rows = {p["id"]: p for p in list_projects(state.conn)}
        projects = scanner.scan_root(root, db_rows, style_id=state.settings.naming_style)
        known = {p["id"] for p in projects}
        for proj in projects:
            row = db_rows.get(proj["id"])
            if row is None or row.get("excluded") or row["path"] != proj["path"]:
                upsert_project(state.conn, proj["id"], proj["name"], proj["type"],
                               proj["path"], proj["description"], imported=False,
                               excluded=bool(row.get("excluded")) if row else False)
        for row in list_projects(state.conn):
            if row["excluded"]:
                continue
            if row["imported"] and row["id"] not in known and Path(row["path"]).is_dir():
                entry = scanner.parse_project_entry(row["id"])
                row["title"] = entry.title if entry else row["id"]
                row["version"] = versioning.read_version(Path(row["path"]))
                row["has_git"] = (Path(row["path"]) / ".git").exists()
                row["has_logo"] = scanner.find_logo(Path(row["path"])) is not None
                row["compliant"] = compliance.quick_compliance(Path(row["path"]), row["type"])
                override = row.get("version_scheme") or ""
                row["version_scheme"] = protocols.version_scheme_for(row["type"], override)
                row["version_scheme_set"] = override
                projects.append(row)
        return sorted(projects, key=lambda pj: (not bool(pj.get("pinned")), 0))

    @api.get("/projects/unmanaged")
    def list_unmanaged_folders() -> list[dict]:
        """未纳管文件夹（严格命名风格下，不符合风格且未导入的根目录文件夹）。"""
        root = state.settings.root
        db_rows = {p["id"]: p for p in list_projects(state.conn)}
        return scanner.list_unmanaged(root, db_rows, style_id=state.settings.naming_style)

    @api.post("/projects", status_code=201)
    def create_project(payload: ProjectCreate) -> dict:
        root = state.settings.root
        root.mkdir(parents=True, exist_ok=True)
        ptype = payload.type
        if ptype not in PROJECT_TYPES and not get_custom_type(state.conn, ptype):
            ptype = "其他"
        folder_name = scanner.make_folder_name(root, ptype, payload.name, style_id=state.settings.naming_style)
        project_path = root / folder_name
        if project_path.exists():
            raise HTTPException(status_code=409, detail="同名项目已存在")
        preset_result = None
        if payload.preset:
            spec = _type_spec(ptype)
            if spec and spec["custom"]:
                preset_result = presets.apply_custom_preset(project_path, spec, payload.name, payload.description, git=True)
            else:
                preset_result = presets.apply_preset(project_path, ptype, payload.name, payload.description, git=True)
        else:
            project_path.mkdir(parents=True, exist_ok=True)
        upsert_project(state.conn, folder_name, folder_name, ptype, str(project_path),
                       payload.description, imported=False)

        github_result = None
        want_github = payload.github if payload.github is not None else state.settings.github_auto
        if want_github and not github.has_remote(project_path):
            if not (project_path / ".git").is_dir():
                presets.ensure_git_commit(project_path)
            if (project_path / ".git").is_dir():
                github_result = github.create_repo(project_path, github.repo_name_for(payload.name),
                                                   state.settings.github_visibility)
            else:
                github_result = {"ok": False, "message": "git 初始化失败，未创建 GitHub 仓库"}

        return {
            "id": folder_name,
            "name": folder_name,
            "type": ptype,
            "title": payload.name,
            "path": str(project_path),
            "description": payload.description,
            "preset": preset_result,
            "github": github_result,
            "version": versioning.read_version(project_path),
        }

    @api.post("/projects/import", status_code=201)
    def import_project(payload: ProjectImport) -> dict:
        try:
            return scanner.import_folder(state.conn, Path(payload.path), payload.type, payload.description)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @api.delete("/projects/{pid}")
    def remove_project(pid: str) -> dict:
        delete_project(state.conn, pid)
        return {"ok": True}

    @api.post("/projects/{pid}/pin")
    def toggle_pin(pid: str) -> dict:
        proj = _resolve_project(pid)
        row = get_project(state.conn, pid)
        if row is None:
            # 仅磁盘扫描到的项目：先注册再置顶，避免静默失败
            upsert_project(state.conn, pid, proj["name"], proj["type"], proj["path"],
                           proj.get("description", ""), imported=bool(proj.get("imported", False)))
            row = get_project(state.conn, pid)
        pinned = not bool(row.get("pinned"))
        set_pinned(state.conn, pid, pinned)
        return {"ok": True, "pinned": pinned, "id": pid}

    @api.post("/projects/{pid}/init")
    def init_project(pid: str, payload: ProjectInit) -> dict:
        proj = _resolve_project(pid)
        ptype = payload.type if payload.type in PROJECT_TYPES or get_custom_type(state.conn, payload.type or "") else proj.get("type", "其他")
        parsed = scanner.parse_project_dir(pid)
        title = payload.name or (parsed[2] if parsed else proj["name"])
        description = payload.description if payload.description is not None else proj.get("description", "")
        spec = _type_spec(ptype)
        if spec and spec["custom"]:
            result = presets.apply_custom_preset(Path(proj["path"]), spec, title, description, git=payload.git)
        else:
            result = presets.apply_preset(Path(proj["path"]), ptype, title, description, git=payload.git)
        upsert_project(state.conn, pid, proj["name"], ptype, proj["path"], description,
                       imported=bool(proj.get("imported", False)))
        return result

    @api.get("/projects/{pid}/ai-logs")
    def list_ai_logs(pid: str, limit: int = 50) -> list[dict]:
        proj = _resolve_project(pid)
        return ailog.list_logs(Path(proj["path"]), limit=max(1, min(limit, 200)))

    @api.post("/projects/{pid}/ai-logs", status_code=201)
    def create_ai_log(pid: str, payload: AILogCreate) -> dict:
        proj = _resolve_project(pid)
        path = ailog.write_log(
            Path(proj["path"]), agent=payload.agent, action=payload.action, result=payload.result,
            summary=payload.summary, details=payload.details, source=payload.source,
        )
        return {"ok": True, "file": path.name}

    @api.post("/projects/{pid}/contract", status_code=201)
    def generate_contract(pid: str, payload: ProjectInit | None = None) -> dict:
        proj = _resolve_project(pid)
        p = Path(proj["path"])
        ptype = proj.get("type") or "其他"
        parsed = scanner.parse_project_dir(pid)
        title = parsed[2] if parsed else proj.get("name", pid)
        path = contract.write_contract(p, ptype, title, proj.get("description", ""), force=True)
        return {"ok": True, "path": str(path)}

    @api.get("/projects/{pid}/compliance")
    def get_compliance(pid: str) -> dict:
        proj = _resolve_project(pid)
        return compliance.check_compliance(Path(proj["path"]), proj.get("type") or "其他")

    @api.post("/projects/{pid}/compliance/fix")
    def run_compliance_fix(pid: str, payload: ComplianceFix) -> dict:
        proj = _resolve_project(pid)
        p = Path(proj["path"])
        ptype = proj.get("type") or "其他"
        report = compliance.check_compliance(p, ptype)
        available = {a["key"]: a for a in report["actions"]}
        unknown = [k for k in payload.actions if k not in available]
        if unknown:
            raise HTTPException(status_code=400, detail="未知的修复动作：" + "、".join(unknown))
        destructive = [k for k in payload.actions if available[k].get("destructive")]
        if destructive and not payload.confirm:
            raise HTTPException(status_code=400, detail="以下动作会移动文件，需勾选确认后执行：" + "、".join(destructive))
        parsed = scanner.parse_project_dir(pid)
        title = parsed[2] if parsed else proj.get("name", pid)
        return compliance.apply_fix(p, ptype, title, proj.get("description", ""),
                                    payload.actions, confirm=payload.confirm)

    @api.get("/projects/{pid}/versions")
    def get_versions(pid: str) -> dict:
        proj = _resolve_project(pid)
        ptype = proj.get("type") or "其他"
        override = proj.get("version_scheme") or ""
        scheme = protocols.version_scheme_for(ptype, override)
        return versioning.project_version_summary(
            Path(proj["path"]), scheme=scheme, build_archive=protocols.build_archive_for(ptype))

    @api.get("/projects/{pid}/git-status")
    def get_git_status(pid: str) -> dict:
        proj = _resolve_project(pid)
        p = Path(proj["path"])
        if not (p / ".git").is_dir():
            return {"has_git": False, "head": None, "dirty": False, "files": []}
        try:
            head = subprocess.run(["git", "log", "--oneline", "-1"], cwd=str(p), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=15,
                                   creationflags=0x08000000 if os.name == "nt" else 0).stdout.strip()
            status = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain"], cwd=str(p), capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=15,
                                    creationflags=0x08000000 if os.name == "nt" else 0).stdout.splitlines()
        except (subprocess.TimeoutExpired, OSError):
            return {"has_git": True, "head": None, "dirty": False, "files": []}
        return {"has_git": True, "head": head or None, "dirty": bool(status),
                "files": [ln.strip()[:120] for ln in status[:30]]}

    @api.get("/projects/{pid}/builds")
    def list_builds(pid: str) -> list[dict]:
        proj = _resolve_project(pid)
        return builder.find_build_scripts(Path(proj["path"]))

    @api.post("/projects/{pid}/build")
    def run_build(pid: str, payload: BuildRun) -> dict:
        proj = _resolve_project(pid)
        scripts = {s["name"]: s for s in builder.find_build_scripts(Path(proj["path"]))}
        script = scripts.get(payload.script)
        if not script:
            raise HTTPException(status_code=404, detail="构建脚本不存在")
        job = state.jobs.start(builder.command_for(script), str(Path(proj["path"])), f"构建 {script['name']}")
        return {"job_id": job.id, "script": script["name"]}

    @api.post("/projects/{pid}/release")
    def run_release(pid: str, payload: ReleaseRun) -> dict:
        proj = _resolve_project(pid)
        version = payload.version.strip()
        if not versioning.VERSION_RE.match("v" + version.lstrip("v")):
            raise HTTPException(status_code=400, detail="版本号格式不正确（应为语义化版本，如 1.2.3）")
        cfg = {"version": version, "changelog": payload.changelog,
               "build_script": payload.build_script, "push": payload.push}
        job = state.jobs.start_task(f"发布 v{version}",
                                    lambda emit: release.run_release(state, Path(proj["path"]), cfg, emit))
        return {"job_id": job.id, "version": version}

    def _assert_inside(project_path: Path, target: str) -> Path:
        p = Path(target).expanduser().resolve()
        base = Path(project_path).resolve()
        if not p.is_file() and not p.is_dir():
            raise HTTPException(status_code=404, detail="文件或目录不存在")
        try:
            p.relative_to(base)
        except ValueError:
            raise HTTPException(status_code=400, detail="路径不在项目目录内")
        return p

    @api.post("/projects/{pid}/icon")
    def set_project_icon(pid: str, payload: IconPayload) -> dict:
        proj = _resolve_project(pid)
        p = Path(proj["path"])
        ptype = proj.get("type") or "其他"
        if payload.mode == "upload":
            if not payload.data:
                raise HTTPException(status_code=400, detail="缺少图片数据")
            try:
                raw = base64.b64decode(str(payload.data).split(",", 1)[-1])
            except Exception:
                raise HTTPException(status_code=400, detail="图片数据无效")
            if not (raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8"
                    or raw[:4] == b"RIFF" or raw[:3] == b"GIF"):
                raise HTTPException(status_code=400, detail="仅支持 PNG/JPEG/WebP/GIF 图片")
            if len(raw) > 8 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="图片过大（>8MB）")
            (p / "logo.png").write_bytes(raw)
        else:
            if payload.symbol is not None and not (0 <= payload.symbol <= 11):
                raise HTTPException(status_code=400, detail="符号编号无效")
            data = iconmaker.make_logo_bytes(ptype, payload.symbol, size=256)
            (p / "logo.png").write_bytes(data)
        return {"ok": True, "has_logo": True, "path": "logo.png"}

    @api.get("/projects/{pid}/logo")
    def project_logo(pid: str):
        proj = _resolve_project(pid)
        logo = scanner.find_logo(Path(proj["path"]))
        if not logo:
            raise HTTPException(status_code=404, detail="该项目没有 logo")
        media = guess_type(str(logo))[0] or "application/octet-stream"
        return FileResponse(str(logo), media_type=media)

    @api.get("/projects/{pid}/documents")
    def list_documents(pid: str, scope: str = "keyword") -> list[dict]:
        proj = _resolve_project(pid)
        if scope == "all":
            return scanner.scan_documents(Path(proj["path"]))
        return scanner.find_documents(Path(proj["path"]))

    @api.get("/projects/{pid}/backups")
    def list_backups(pid: str) -> list[dict]:
        proj = _resolve_project(pid)
        return backup.list_backups(Path(proj["path"]))

    @api.post("/projects/{pid}/backups", status_code=201)
    def create_backup(pid: str) -> dict:
        proj = _resolve_project(pid)
        try:
            path = backup.make_backup(Path(proj["path"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        st = path.stat()
        return {"ok": True, "name": path.name, "path": str(path), "size": st.st_size}

    @api.post("/projects/{pid}/backups/restore")
    def restore_backup(pid: str, payload: BackupRestore) -> dict:
        proj = _resolve_project(pid)
        if not payload.confirm:
            raise HTTPException(status_code=400, detail="恢复会覆盖当前项目文件，请确认后重试")
        try:
            result = backup.restore_backup(Path(proj["path"]), payload.name)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, **result}

    @api.delete("/projects/{pid}/backups/{name}")
    def remove_backup(pid: str, name: str) -> dict:
        proj = _resolve_project(pid)
        try:
            deleted = backup.delete_backup(Path(proj["path"]), name)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not deleted:
            raise HTTPException(status_code=404, detail="备份不存在")
        return {"ok": True}

    @api.post("/projects/{pid}/open-file")
    def open_file(pid: str, payload: OpenPath) -> dict:
        proj = _resolve_project(pid)
        target = _assert_inside(Path(proj["path"]), payload.path)
        if os.name != "nt":
            raise HTTPException(status_code=400, detail="当前平台暂不支持打开文件")
        os.startfile(str(target))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(target)}

    @api.post("/projects/{pid}/reveal-file")
    def reveal_file(pid: str, payload: OpenPath) -> dict:
        proj = _resolve_project(pid)
        target = _assert_inside(Path(proj["path"]), payload.path)
        if os.name != "nt":
            raise HTTPException(status_code=400, detail="当前平台暂不支持")
        subprocess.Popen(["explorer", "/select,", str(target)])
        return {"ok": True, "path": str(target)}

    @api.post("/projects/{pid}/open")
    def open_project(pid: str) -> dict:
        proj = _resolve_project(pid)
        if os.name != "nt":
            raise HTTPException(status_code=400, detail="当前平台暂不支持打开文件夹")
        os.startfile(proj["path"])  # type: ignore[attr-defined]
        return {"ok": True}

    @api.put("/projects/{pid}")
    def update_project(pid: str, payload: ProjectUpdate) -> dict:
        """编辑项目信息：name 重命名标题、type 更新类型、description 存库、version_scheme 覆盖版本方案。"""
        proj = _resolve_project(pid)
        if payload.version_scheme is not None and payload.version_scheme not in ("", *protocols.VERSION_SCHEMES):
            raise HTTPException(status_code=400, detail="未知的版本方案")
        old_path = Path(proj["path"])
        old_row = get_project(state.conn, pid) or {}
        ptype = payload.type or proj.get("type", "其他")
        entry = scanner.parse_project_entry(pid)
        current_title = entry.title if entry else proj.get("name", pid)
        title = (payload.name or "").strip() or current_title
        description = payload.description if payload.description is not None else proj.get("description", "")
        if entry is not None:
            # 保留原风格与原序号（local 风格的 2.1 子序号也原样保留）
            new_name = naming.make_name(entry.style, entry.index_raw, ptype, scanner.sanitize_title(title))
        else:
            new_name = scanner.sanitize_title(title) if (payload.name or "").strip() else pid
        new_path = old_path
        if new_name != pid:
            target = old_path.parent / new_name
            if target.exists():
                raise HTTPException(status_code=400, detail=f"目标文件夹已存在：{new_name}")
            try:
                os.rename(old_path, target)
            except OSError as exc:
                raise HTTPException(status_code=400, detail=f"重命名失败：{exc}")
            new_path = target
            delete_project(state.conn, pid)
        upsert_project(state.conn, new_path.name, new_path.name, ptype, str(new_path),
                       description, imported=bool(proj.get("imported", False)),
                       pinned=bool(old_row.get("pinned", False)))
        if payload.version_scheme is not None:
            set_version_scheme(state.conn, new_path.name, payload.version_scheme)
        entry = scanner.parse_project_entry(new_path.name)
        override = (payload.version_scheme if payload.version_scheme is not None
                    else (old_row.get("version_scheme") or ""))
        return {
            "id": new_path.name,
            "name": new_path.name,
            "type": ptype,
            "title": entry.title if entry else new_path.name,
            "path": str(new_path),
            "description": description,
            "imported": bool(proj.get("imported", False)),
            "pinned": bool(old_row.get("pinned", False)),
            "version_scheme": protocols.version_scheme_for(ptype, override),
            "version_scheme_set": override,
        }

    @api.get("/github/auth")
    def github_auth_status() -> dict:
        token = ghrepo.resolve_token(state.settings)
        user = ghrepo.gh_user(token)
        source = "token" if state.settings.github_token else ("gh" if user else "none")
        return {"logged_in": bool(user), "source": source, "user": user}

    @api.post("/github/auth")
    def github_auth_login(payload: GithubAuthPayload) -> dict:
        token = (payload.token or "").strip()
        user = ghrepo.gh_user(token)
        if not user:
            raise HTTPException(status_code=400, detail="令牌无效或已过期，请检查后重试")
        state.settings.update(github_token=token)
        return {"ok": True, "user": user}

    @api.delete("/github/auth")
    def github_auth_logout() -> dict:
        state.settings.update(github_token="")
        return {"ok": True}

    @api.post("/open-url")
    def open_url(payload: OpenUrl) -> dict:
        url = (payload.url or "").strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="仅支持 http/https 链接")
        try:
            if os.name == "nt":
                os.startfile(url)  # type: ignore[attr-defined]
            else:
                import webbrowser
                webbrowser.open(url)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"打开失败：{exc}")
        return {"ok": True, "url": url}

    @api.get("/projects/{pid}/github")
    def project_github(pid: str) -> dict:
        proj = _resolve_project(pid)
        token = ghrepo.resolve_token(state.settings)
        user = ghrepo.gh_user(token)
        remote = ghrepo.remote_of(Path(proj["path"]))
        slug = ghrepo.parse_remote_url(remote) if remote else None
        repo = None
        if slug and user:
            try:
                repo = ghrepo.repo_info(token, slug[0], slug[1])
            except ghrepo.GhError as exc:
                repo = {"error": str(exc)}
        source = "token" if state.settings.github_token else ("gh" if user else "none")
        return {
            "auth": {"logged_in": bool(user), "source": source, "user": user},
            "remote": {"url": remote or "", "owner": slug[0] if slug else "", "repo": slug[1] if slug else ""},
            "repo": repo,
        }

    @api.get("/projects/{pid}/github/readme")
    def project_github_readme(pid: str) -> dict:
        proj = _resolve_project(pid)
        token = ghrepo.resolve_token(state.settings)
        slug = ghrepo.repo_slug(Path(proj["path"]))
        if not slug:
            raise HTTPException(status_code=400, detail="项目未配置 GitHub 远程仓库")
        if not token:
            raise HTTPException(status_code=400, detail="未登录 GitHub，请先在设置中登录")
        try:
            try:
                info = ghrepo.repo_info(token, slug[0], slug[1])
                branch = str(info.get("default_branch") or "main")
            except ghrepo.GhError:
                branch = "main"
            text = ghrepo.repo_readme(token, slug[0], slug[1])
        except ghrepo.GhError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"text": text, "owner": slug[0], "repo": slug[1], "branch": branch}

    @api.get("/projects/{pid}/github/commits")
    def project_github_commits(pid: str, limit: int = 10) -> dict:
        proj = _resolve_project(pid)
        token = ghrepo.resolve_token(state.settings)
        slug = ghrepo.repo_slug(Path(proj["path"]))
        if not slug or not token:
            return {"commits": []}
        try:
            commits = ghrepo.repo_commits(token, slug[0], slug[1], limit=max(1, min(limit, 50)))
        except ghrepo.GhError:
            commits = []
        return {"commits": commits}

    @api.get("/projects/{pid}/github/releases")
    def project_github_releases(pid: str, limit: int = 8) -> dict:
        proj = _resolve_project(pid)
        token = ghrepo.resolve_token(state.settings)
        slug = ghrepo.repo_slug(Path(proj["path"]))
        if not slug or not token:
            return {"releases": []}
        try:
            releases = ghrepo.repo_releases(token, slug[0], slug[1], limit=max(1, min(limit, 30)))
        except ghrepo.GhError:
            releases = []
        return {"releases": releases}

    @api.post("/projects/{pid}/github/create")
    def project_github_create(pid: str, payload: GithubCreatePayload) -> dict:
        proj = _resolve_project(pid)
        token = ghrepo.resolve_token(state.settings)
        parsed = scanner.parse_project_dir(pid)
        name = github.repo_name_for(parsed[2] if parsed else proj["name"])
        visibility = payload.visibility if payload.visibility in ("private", "public") else "private"
        result = ghrepo.create_repo(Path(proj["path"]), name, visibility, token, proj.get("description", ""))
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("message", "创建失败"))
        return result

    @api.get("/projects/{pid}/techstack")
    def project_techstack(pid: str) -> dict:
        proj = _resolve_project(pid)
        return techstack.read_techstack(Path(proj["path"]))

    @api.put("/projects/{pid}/techstack")
    def project_techstack_save(pid: str, payload: TechstackPayload) -> dict:
        proj = _resolve_project(pid)
        return techstack.write_techstack(Path(proj["path"]), payload.content)

    @api.post("/projects/{pid}/techstack/template")
    def project_techstack_template(pid: str) -> dict:
        proj = _resolve_project(pid)
        title = scanner.parse_project_dir(pid)[2] if scanner.parse_project_dir(pid) else proj["name"]
        return techstack.ensure_template(Path(proj["path"]), title)

    @api.post("/projects/{pid}/github/set-remote")
    def project_github_set_remote(pid: str, payload: GithubSetRemotePayload) -> dict:
        proj = _resolve_project(pid)
        result = ghrepo.set_remote(Path(proj["path"]), (payload.url or "").strip())
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("message", "设置失败"))
        return result


    @api.get("/jobs")
    def list_jobs(limit: int = 30) -> list[dict]:
        return state.jobs.list(limit=limit)

    @api.get("/console")
    def console_overview() -> dict:
        root = state.settings.root
        activity = console.collect_activity(root, limit=30)
        projects = []
        for pj in scanner.scan_root(root, {p2["id"]: p2 for p2 in list_projects(state.conn)}):
            last = next((e for e in activity if e.get("project") == pj["id"]), None)
            projects.append({
                "id": pj["id"], "title": pj["title"], "type": pj["type"],
                "version": pj["version"], "compliant": pj["compliant"],
                "has_git": pj["has_git"], "last_log": last,
            })
        return {
            "activity": activity,
            "running_jobs": [j for j in state.jobs.list() if j["status"] == "running"],
            "failed_count": sum(1 for e in activity if e.get("result") == "failed"),
            "projects": projects,
        }

    @api.post("/agent/batch")
    def run_agent_batch(payload: AgentBatch) -> dict:
        agent = _resolve_agent(payload.agent)
        jobs = []
        for pid in payload.project_ids:
            try:
                proj = _resolve_project(pid)
            except HTTPException:
                jobs.append({"project_id": pid, "job_id": None, "error": "项目不存在"})
                continue
            spec = _type_spec(proj.get("type", "其他"))
            context = agent_mod.system_prompt(proj["name"], proj["path"], spec, state.settings.confirm_policy)
            task = payload.prompt + "\n\n请直接在当前项目目录执行上述任务并完成实际文件/代码/版本操作（不要只做介绍或说明）；完成后用中文简短报告你做了什么。"
            job = state.jobs.start_task(
                f"批量·{proj['name']}", lambda emit, pj=Path(proj["path"]), pr=task, ag=agent, cx=context:
                agent_mod.run_agent_task(state, pj, ag, pr, emit, context=cx))
            jobs.append({"project_id": pid, "job_id": job.id})
        return {"jobs": jobs, "agent": agent}

    @api.get("/update/check")
    def update_check() -> dict:
        return update.check_update(APP_VERSION, state.settings.update_repo)

    @api.post("/update/download")
    def update_download() -> dict:
        repo = state.settings.update_repo
        rel = update.latest_release(repo)
        if not rel or not rel.get("tag"):
            raise HTTPException(status_code=400, detail="无法获取最新版本信息（请确认已安装 gh 并登录）")
        result = update.download_setup(repo, rel["tag"], update.update_temp_dir())
        if not result["ok"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"ok": True, "path": result["path"], "size": result["size"], "tag": rel["tag"]}

    @api.post("/update/install")
    def update_install(payload: UpdateInstall) -> dict:
        result = update.install_setup(payload.path)
        if not result["ok"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"ok": True}

    @api.get("/agents")
    def list_agents() -> list[dict]:
        return [{"name": k, "label": v["label"], "hint": v["hint"]} for k, v in AGENTS.items()]

    @api.post("/agent/run")
    def run_agent(payload: AgentRun) -> dict:
        proj = _resolve_project(payload.project_id)
        agent = _resolve_agent(payload.agent)
        spec = _type_spec(proj.get("type", "其他"))
        context = agent_mod.system_prompt(proj["name"], proj["path"], spec,
                                          state.settings.confirm_policy,
                                          history=getattr(payload, "history", None))
        task = payload.prompt + "\n\n请直接在当前项目目录执行上述任务并完成实际文件/代码/版本操作（不要只做介绍或说明）；完成后用中文简短报告你做了什么。"
        job = state.jobs.start_task(
            f"AI · {AGENTS[agent]['label']}",
            lambda emit: agent_mod.run_agent_task(state, Path(proj["path"]), agent, task, emit, context=context),
        )
        return {"job_id": job.id, "agent": agent, "backup": state.settings.backup}

    @api.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        status = state.jobs.status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        return status

    @api.get("/jobs/{job_id}/stream")
    async def job_stream(job_id: str, request: Request):
        job = state.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")

        async def gen():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        item = await asyncio.to_thread(job.queue.get, timeout=0.5)
                    except (TimeoutError, queue_module.Empty):
                        continue
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    if item.get("type") == "end":
                        break
            except Exception:
                pass

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.include_router(api)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
    else:
        @app.get("/")
        def web_missing() -> JSONResponse:
            return JSONResponse({"ok": True, "note": "web/ 前端目录缺失，仅 API 可用"})

    return app
