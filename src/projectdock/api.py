from __future__ import annotations

import asyncio
import json
import os
import queue as queue_module
import subprocess
import sys
from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agent as agent_mod
from . import ailog, builder, compliance, console, contract, github, presets, release, scanner, update, versioning
from .agent import AGENTS
from .config import APP_NAME, APP_VERSION
from .db import delete_custom_type, delete_project, get_custom_type, get_project, list_custom_types, list_projects, upsert_custom_type, upsert_project
from .models import (AGENT_NAMES, PROJECT_TYPES, THEMES, AILogCreate, AgentBatch, AgentRun,
                     BuildRun, ComplianceFix, CustomTypeCreate, OpenPath, ProjectCreate,
                     ProjectImport, ProjectInit, ReleaseRun, SettingsUpdate, UpdateInstall)
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
            parsed = scanner.parse_project_dir(pid)
            return {"id": pid, "name": pid, "type": parsed[1] if parsed else "其他",
                    "path": str(p), "description": ""}
        raise HTTPException(status_code=404, detail="项目不存在")

    def _type_spec(ptype: str) -> dict | None:
        if ptype in presets.PRESETS:
            spec = presets.PRESETS[ptype]
            return {
                "name": ptype, "label": spec["label"], "description": spec["description"],
                "dirs": spec.get("dirs", []), "files": spec.get("files", {}),
                "git": spec.get("git", True), "custom": False,
            }
        row = get_custom_type(state.conn, ptype)
        if row:
            return {
                "name": row["name"], "label": row["label"], "description": row["description"],
                "dirs": json.loads(row["dirs"]), "files": json.loads(row["files"]),
                "git": bool(row["git"]), "custom": True,
            }
        return None

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
        return state.settings.update(
            root=payload.root, agent=payload.agent, theme=payload.theme,
            github_auto=payload.github_auto, github_visibility=payload.github_visibility,
            backup=payload.backup, type_tabs=payload.type_tabs,
            confirm_policy=payload.confirm_policy,
            update_repo=payload.update_repo,
        )

    @api.get("/presets")
    def list_presets() -> list[dict]:
        out = []
        for t, spec in presets.PRESETS.items():
            out.append({
                "type": t, "label": spec["label"], "description": spec["description"],
                "files": list(spec.get("files", {})), "dirs": list(spec.get("dirs", [])),
                "git": spec.get("git", True), "custom": False,
            })
        for row in list_custom_types(state.conn):
            out.append({
                "type": row["name"], "label": row["label"], "description": row["description"],
                "files": list(json.loads(row["files"])), "dirs": json.loads(row["dirs"]),
                "git": bool(row["git"]), "custom": True,
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
                "tab_labels": presets.TAB_LABELS,
            })
        for row in list_custom_types(state.conn):
            ptype = row["name"]
            out.append({
                "name": ptype, "label": row["label"], "description": row["description"],
                "dirs": json.loads(row["dirs"]), "files": json.loads(row["files"]),
                "git": bool(row["git"]), "custom": True,
                "tabs": presets.tabs_for_type(ptype, override),
                "tab_labels": presets.TAB_LABELS,
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
        projects = scanner.scan_root(root, db_rows)
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
                parsed = scanner.parse_project_dir(row["id"])
                row["title"] = parsed[2] if parsed else row["id"]
                row["version"] = versioning.read_version(Path(row["path"]))
                row["has_git"] = (Path(row["path"]) / ".git").exists()
                row["has_logo"] = scanner.find_logo(Path(row["path"])) is not None
                row["compliant"] = compliance.quick_compliance(Path(row["path"]), row["type"])
                projects.append(row)
        return projects

    @api.post("/projects", status_code=201)
    def create_project(payload: ProjectCreate) -> dict:
        root = state.settings.root
        root.mkdir(parents=True, exist_ok=True)
        ptype = payload.type
        if ptype not in PROJECT_TYPES and not get_custom_type(state.conn, ptype):
            ptype = "其他"
        folder_name = scanner.make_folder_name(root, ptype, payload.name)
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
        return versioning.project_version_summary(Path(proj["path"]))

    @api.get("/projects/{pid}/git-status")
    def get_git_status(pid: str) -> dict:
        proj = _resolve_project(pid)
        p = Path(proj["path"])
        if not (p / ".git").is_dir():
            return {"has_git": False, "head": None, "dirty": False, "files": []}
        try:
            head = subprocess.run(["git", "log", "--oneline", "-1"], cwd=str(p), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=15).stdout.strip()
            status = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain"], cwd=str(p), capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=15).stdout.splitlines()
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
        agent = payload.agent if payload.agent in AGENT_NAMES else state.settings.agent
        jobs = []
        for pid in payload.project_ids:
            try:
                proj = _resolve_project(pid)
            except HTTPException:
                jobs.append({"project_id": pid, "job_id": None, "error": "项目不存在"})
                continue
            spec = _type_spec(proj.get("type", "其他"))
            prompt = agent_mod.system_prompt(proj["name"], proj["path"], spec, state.settings.confirm_policy) + "\n\n用户要求：" + payload.prompt
            job = state.jobs.start_task(
                f"批量·{proj['name']}", lambda emit, pj=Path(proj["path"]), pr=prompt, ag=agent:
                agent_mod.run_agent_task(state, pj, ag, pr, emit))
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
        agent = payload.agent if payload.agent in AGENT_NAMES else state.settings.agent
        spec = _type_spec(proj.get("type", "其他"))
        prompt = agent_mod.system_prompt(proj["name"], proj["path"], spec, state.settings.confirm_policy) + "\n\n用户要求：" + payload.prompt
        job = state.jobs.start_task(
            f"AI · {AGENTS[agent]['label']}",
            lambda emit: agent_mod.run_agent_task(state, Path(proj["path"]), agent, prompt, emit),
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
                    except (asyncio.TimeoutError, queue_module.Empty):
                        continue
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    if item.get("type") == "end":
                        break
            except Exception:  # noqa: BLE001
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
